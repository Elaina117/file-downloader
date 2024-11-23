import os
import subprocess
import urllib.parse
import requests
import signal
import json
from modules import script_callbacks, shared
import gradio as gr

class Downloader:
    def __init__(self):
        self.process = None
        self.cancelled = False
    
    def cancel_download(self):
        if self.process:
            if os.name == 'nt': self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else: self.process.terminate()
            self.cancelled = True
            return "ダウンロードをキャンセルしました"
        return "ダウンロードは実行されていません"

downloader = Downloader()

def get_model_path(model_type):
    paths = {'ckpt': 'models/Stable-diffusion', 'vae': 'models/VAE', 'lora': 'models/Lora'}
    return paths.get(model_type, '')

def get_civitai_api_key():
    try:
        config_path = os.path.join(shared.cmd_opts.config, 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get('custom_api_key', '')
    except: pass
    return ''

def modify_civitai_url(url):
    if 'civitai.com' in url:
        api_key = get_civitai_api_key()
        if api_key:
            separator = '&' if '?' in url else '?'
            url = f"{url}{separator}token={api_key}"
    return url

def check_download_availability(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        
        if response.status_code != 200:
            return False, None, f"エラー: サーバーからエラーコード {response.status_code} が返されました"
            
        content_length = response.headers.get('Content-Length')
        if content_length is not None and int(content_length) == 0:
            return False, None, "エラー: ファイルサイズが0バイトです"
        
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type.lower():
            return False, None, "エラー: このURLは直接ダウンロード可能なファイルではありません"
            
        filename = None
        if 'Content-Disposition' in response.headers:
            import cgi
            value, params = cgi.parse_header(response.headers['Content-Disposition'])
            if 'filename*' in params:
                encoding, _, fname = params['filename*'].split("'")
                filename = urllib.parse.unquote(fname)
            elif 'filename' in params:
                filename = params['filename']
        
        if not filename:
            filename = os.path.basename(urllib.parse.unquote(url))
            
        if not filename or not any(c not in '<>:"/\\|?*' for c in filename):
            return False, None, "エラー: 不正なファイル名です"
            
        return True, filename, None
        
    except requests.Timeout:
        return False, None, "エラー: サーバーの応答がタイムアウトしました"
    except requests.RequestException as e:
        return False, None, f"エラー: 接続エラー: {str(e)}"
    except Exception as e:
        return False, None, f"エラー: {str(e)}"

def parse_aria2c_output(line):
    try:
        if '[' in line and ']' in line:
            parts = line.split()
            for part in parts:
                if '%' in part: progress = float(part.strip('%'))
                if '/s' in part: speed = part
                if '(' in part and ')' in part and ':' in part: eta = part.strip('()')
            return progress, speed, eta
    except: pass
    return None, None, None

def download_with_aria2c(url, save_path, progress=gr.Progress()):
    if not url.strip():
        return "URLを入力してください"

    url = modify_civitai_url(url)
    is_available, filename, error_message = check_download_availability(url)
    if not is_available:
        return error_message

    downloader.cancelled = False
    save_dir = os.path.abspath(save_path)
    os.makedirs(save_dir, exist_ok=True)
    full_save_path = os.path.join(save_dir, filename)
    
    command = [
        'aria2c', '--summary-interval=1', '-x16', '-s16',
        '--file-allocation=none', '-k1M', '--max-tries=3', '-m0',
        '--show-console-readout=true', '--auto-file-renaming=true',
        '-d', save_dir, '-o', filename, url
    ]
    
    try:
        downloader.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        while True:
            line = downloader.process.stdout.readline()
            if not line and downloader.process.poll() is not None:
                break
            
            progress_val, speed, eta = parse_aria2c_output(line)
            if progress_val is not None:
                status = f"進捗: {progress_val:.1f}% | 速度: {speed} | 残り時間: {eta}"
                progress(progress_val / 100, desc=status)
            
            if downloader.cancelled:
                return "ダウンロードがキャンセルされました"
        
        if downloader.process.returncode == 0:
            return f"ダウンロード完了: {full_save_path}"
        else:
            stderr = downloader.process.stderr.read()
            return f"ダウンロードエラー: {stderr}"
            
    except FileNotFoundError:
        return "エラー: aria2cがインストールされていません"
    except Exception as e:
        return f"エラー: {str(e)}"
    finally:
        downloader.process = None

def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as downloader_interface:
        # JavaScript の定義
        gr.HTML("""
            <script>
            function setModelPath(path) {
                // 保存先フォルダの入力欄を検索
                const inputs = Array.from(document.getElementsByTagName('input'));
                const textarea = inputs.find(input => input.placeholder === "保存先フォルダを入力");
                if (textarea) {
                    textarea.value = path;
                    // イベントを発火させて Gradio に変更を通知
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
            </script>
        """)

        with gr.Row():
            url_input = gr.Textbox(
                label="ダウンロードURL",
                placeholder="URLを入力してください"
            )
            
        with gr.Row():
            lora_btn = gr.Button("LoRA")
            ckpt_btn = gr.Button("CKPT")
            vae_btn = gr.Button("VAE")
            
        with gr.Row():
            save_path_input = gr.Textbox(
                label="保存先フォルダ",
                placeholder="保存先フォルダを入力",
                value="downloads/"
            )
            
        with gr.Row():
            download_btn = gr.Button("ダウンロード開始", variant="primary")
            cancel_btn = gr.Button("キャンセル", variant="stop")
            
        result_text = gr.Textbox(
            label="実行結果",
            interactive=False
        )

        # モデルパスの設定を JavaScript で処理
        lora_btn.click(
            fn=None,
            outputs=None,
            _js="() => setModelPath('models/Lora/')"
        )

        ckpt_btn.click(
            fn=None,
            outputs=None,
            _js="() => setModelPath('models/Stable-diffusion/')"
        )

        vae_btn.click(
            fn=None,
            outputs=None,
            _js="() => setModelPath('models/VAE/')"
        )
        
        download_btn.click(
            fn=download_with_aria2c,
            inputs=[url_input, save_path_input],
            outputs=result_text
        )
        
        cancel_btn.click(
            fn=downloader.cancel_download,
            outputs=result_text
        )
    
    return [(downloader_interface, "ファイルダウンローダー", "file_downloader_tab")]

script_callbacks.on_ui_tabs(on_ui_tabs)