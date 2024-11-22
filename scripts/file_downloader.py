import os
import subprocess
import urllib.parse
import requests
from modules import script_callbacks, shared
import gradio as gr

def get_filename_from_url(url):
    """
    URLからContent-Dispositionヘッダーを取得してファイル名を抽出する
    ヘッダーが存在しない場合はURLの最後の部分を使用
    """
    try:
        response = requests.head(url, allow_redirects=True)
        if 'Content-Disposition' in response.headers:
            import cgi
            value, params = cgi.parse_header(response.headers['Content-Disposition'])
            if 'filename*' in params:
                # RFC 5987形式のエンコードされたファイル名を処理
                encoding, _, fname = params['filename*'].split("'")
                return urllib.parse.unquote(fname)
            elif 'filename' in params:
                return params['filename']
    except:
        pass
    
    # ヘッダーからファイル名を取得できない場合はURLから取得
    return os.path.basename(urllib.parse.unquote(url))

def download_with_aria2c(url, save_path, progress=gr.Progress()):
    """
    aria2cを使用してファイルをダウンロードする
    """
    # 保存先ディレクトリの作成
    save_dir = os.path.dirname(save_path)
    os.makedirs(save_dir, exist_ok=True)
    
    # ファイル名の取得
    filename = get_filename_from_url(url)
    full_save_path = os.path.join(save_dir, filename)
    
    # aria2cコマンドの設定
    command = [
        'aria2c',
        '--summary-interval=1',  # 進捗更新間隔
        '-x16',                  # 最大接続数
        '-s16',                  # 分割数
        '--file-allocation=none', # 事前確保なし
        '-k1M',                  # 分割サイズ
        '--max-tries=3',         # リトライ回数
        '-m0',                   # リトライ間隔
        '--console-log-level=error',
        '-d', save_dir,         # 保存先ディレクトリ
        '-o', filename,         # 出力ファイル名
        url
    ]
    
    try:
        # aria2cプロセスの実行
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        progress(0, desc=f"ダウンロード中: {filename}")
        
        # プロセスの完了を待機
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            return f"ダウンロード完了: {full_save_path}"
        else:
            return f"ダウンロードエラー: {stderr}"
            
    except FileNotFoundError:
        return "エラー: aria2cがインストールされていません。インストールしてください。"
    except Exception as e:
        return f"エラー: {str(e)}"

def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as downloader_interface:
        with gr.Row():
            url_input = gr.Textbox(
                label="ダウンロードURL",
                placeholder="URLを入力してください"
            )
            save_path_input = gr.Textbox(
                label="保存先フォルダ",
                placeholder="保存先フォルダを入力 (例: models/lora/)",
                value="downloads/"
            )
        
        with gr.Row():
            download_button = gr.Button("ダウンロード開始", variant="primary")
        
        result_text = gr.Textbox(
            label="実行結果",
            interactive=False
        )
        
        info_text = gr.Markdown("""
        ### 使い方
        1. ダウンロードしたいファイルのURLを入力
        2. 保存先フォルダを指定
        3. 「ダウンロード開始」ボタンをクリック
        
        ### 特徴
        - aria2cによる高速ダウンロード
        - 自動ファイル名取得
        - 最大16並列ダウンロード
        - 自動リトライ機能
        """)
        
        download_button.click(
            fn=download_with_aria2c,
            inputs=[url_input, save_path_input],
            outputs=result_text
        )
    
    return [(downloader_interface, "ファイルダウンローダー", "file_downloader_tab")]

# Stable Diffusion Web UIに拡張機能を登録
script_callbacks.on_ui_tabs(on_ui_tabs)