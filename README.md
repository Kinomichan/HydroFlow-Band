# M5StickS3 / Grove GSR Sensor Reader

M5StickS3 と Seeed Studio Grove GSR（皮膚電気活動）センサーを接続し、皮膚電気抵抗値を測定・モニタリングする MicroPython プロジェクトです。

---

## 1. 接続仕様

M5StickS3 の Grove ポート (Port A) に GSR センサーを接続します。

* **アナログ信号 (SIG/SDA)**: M5StickS3 の **GPIO 1** (ADC チャンネル) に接続されます。
* **電源 (5V VCC)**: Grove センサーを動作させるため、内部の PMIC (PY32L020) に対し、内部 I2C (SDA: GPIO 11, SCL: GPIO 12) を通じて 5V 昇圧回路 (5V Boost) を有効化して電源を供給します。

---

## 2. ファイル構成

* **[main.py](file:///home/karube/GitHub/M5StickS3/main.py)**: M5StickS3 起動時に自動実行されるメインプログラム。PMICの初期化、5V電源の有効化、ADCからのサンプリング、抵抗値への変換式処理を行います。
* **[gsr_reader.py](file:///home/karube/GitHub/M5StickS3/gsr_reader.py)**: `main.py` と同内容のバックアップコードです。
* **[sync.py](file:///home/karube/GitHub/M5StickS3/sync.py)**: 開発PCから M5StickS3 にソースファイルを書き込み、同期するための自動化スクリプト。

---

## 3. 環境構築

本プロジェクトは Python の仮想環境 `.venv` 内の `mpremote` ライブラリを使用して M5StickS3 と通信します。

```bash
# 仮想環境を作成 (未作成の場合)
python3 -m venv .venv

# 依存パッケージ (mpremote, pyserial) をインストール
.venv/bin/python -m pip install mpremote
```

---

## 4. 同期スクリプト (sync.py) の使い方

ローカルのソースコードを M5StickS3 に書き込み、自動的に再起動します。`.git` や `.venv`、`sync.py` などの不要なファイルは自動で除外されます。

### 基本的な書き込み (ローカルファイルの追加/上書き)
```bash
./sync.py
```
*(同期対象のファイル一覧が表示された後、`y/N` で確認プロンプトが表示されます。)*

### ミラーリング同期 (ローカルに存在しないリモート側のファイルを削除)
ローカルから削除したファイルを M5StickS3 側からも削除し、同期したい場合に使用します。システムファイル `boot.py` は自動的に削除から保護されます。
```bash
./sync.py -c
```

### オプション一覧
```bash
./sync.py [-h] [-p PORT] [-y] [-c]
```
* `-h, --help`: ヘルプを表示。
* `-p, --port`: シリアルポートを指定 (デフォルト: `/dev/ttyACM0`)。
* `-y, --yes`: 実行前の確認プロンプトをスキップ。
* `-c, --clean`: ミラーリング（不要ファイルのクリーンアップ）を有効にする。

---

## 5. トラブルシューティング

### エラー: `Failed to connect. The port is currently in use`
Thonny IDE などの他のプログラムが `/dev/ttyACM0` への接続を開きっぱなしにしている可能性があります。
* **解決策**: Thonny などのシリアル接続を切断、もしくは IDE 自体を終了してから実行してください。

### エラー: `Could not enter raw REPL`
ESP32-S3 のネイティブ USB CDC において、マイコンがフリーズしているか、シリアル入力の割り込みを正しく処理できない状態になっている場合に発生します。
* **解決策**:
  1. M5StickS3 の側面にある**赤い物理RESETボタン**を一度押してください。
  2. USB ケーブルを一度抜き差ししてください。
  3. Thonny などのシリアルモニターが完全に閉じていることを確認してください。
