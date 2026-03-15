#!/usr/bin/env python3
"""
Claude Code テレメトリデータをPrometheusからエクスポートするスクリプト
累積値（生データ）を保存するバージョン
"""

import os
import requests
import json
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# 設定
# Docker内で実行する場合はprometheus、ローカルで実行する場合はlocalhost
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
OUTPUT_DIR = Path("/data/telemetry") if os.path.exists("/data/telemetry") else Path(__file__).parent.parent / "data" / "telemetry"

# 取得するメトリクス
METRICS = [
    "claude_code_cost_usage_USD_total",
    "claude_code_token_usage_tokens_total",
    "claude_code_lines_of_code_count_total",
    "claude_code_session_count_total",
    "claude_code_code_edit_tool_decision_total",
    "claude_code_active_time_total_seconds",
    "claude_code_pull_request_count_total",
    "claude_code_commit_count_total",
]

def fetch_metric(metric_name):
    """Prometheusから特定のメトリクスを取得"""
    try:
        url = f"{PROMETHEUS_URL}/api/v1/query"
        params = {"query": metric_name}

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get('status') != 'success':
            print(f"  Warning: {metric_name} - status: {data.get('status')}")
            return None

        result = data.get('data', {}).get('result', [])
        if not result:
            print(f"  Info: {metric_name} - no data")
            return None

        print(f"  ✓ {metric_name} - {len(result)} data points")
        return {
            'metric_name': metric_name,
            'timestamp': datetime.now().isoformat(),
            'data': result
        }

    except requests.exceptions.RequestException as e:
        print(f"  Error fetching {metric_name}: {e}")
        return None

def save_to_file(metrics_data):
    """メトリクスデータをファイルに保存（累積値）"""
    if not metrics_data:
        return None

    # 出力ディレクトリを作成
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 日付ごとのファイル名
    date_str = datetime.now().strftime('%Y-%m-%d')
    output_file = OUTPUT_DIR / f"metrics-{date_str}.jsonl"

    # JSONL形式で追記
    saved_count = 0
    with open(output_file, 'a', encoding='utf-8') as f:
        for metric_data in metrics_data:
            if metric_data:
                json.dump(metric_data, f, ensure_ascii=False)
                f.write('\n')
                saved_count += 1

    if saved_count > 0:
        print(f"\n✓ Saved to: {output_file}")
        print(f"  File size: {output_file.stat().st_size / 1024:.2f} KB")
        print(f"  Entries saved: {saved_count}")
        return output_file

    return None

def archive_old_files():
    """7日より古いJSONLファイルをgzip圧縮"""
    threshold_date = datetime.now() - timedelta(days=7)
    archived_count = 0

    print(f"\n--- Checking for files older than {threshold_date.strftime('%Y-%m-%d')} ---")

    for jsonl_file in sorted(OUTPUT_DIR.glob("metrics-*.jsonl")):
        try:
            # ファイル名から日付を抽出（metrics-YYYY-MM-DD.jsonl）
            date_str = jsonl_file.stem.replace("metrics-", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")

            if file_date < threshold_date:
                # gzip圧縮
                gz_file = jsonl_file.with_suffix('.jsonl.gz')
                print(f"  Archiving {jsonl_file.name}...", end=" ")

                with open(jsonl_file, 'rb') as f_in:
                    with gzip.open(gz_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # 元ファイルを削除
                original_size = jsonl_file.stat().st_size
                compressed_size = gz_file.stat().st_size
                jsonl_file.unlink()

                compression_ratio = (1 - compressed_size / original_size) * 100
                print(f"✓ ({original_size/1024:.1f}KB → {compressed_size/1024:.1f}KB, {compression_ratio:.1f}% reduced)")
                archived_count += 1

        except Exception as e:
            print(f"  Error archiving {jsonl_file.name}: {e}")

    if archived_count > 0:
        print(f"✓ Archived {archived_count} file(s)")
    else:
        print(f"  No files to archive")

def main():
    """メイン処理"""
    print(f"=== Claude Code Telemetry Export (Raw Data Mode) ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Prometheus: {PROMETHEUS_URL}")
    print(f"\nFetching {len(METRICS)} metrics...\n")

    # 全メトリクスを取得（累積値をそのまま保存）
    all_metrics = []
    for metric_name in METRICS:
        metric_data = fetch_metric(metric_name)
        if metric_data:
            all_metrics.append(metric_data)

    # ファイルに保存
    if all_metrics:
        save_to_file(all_metrics)
        print(f"\n✓ Export complete - {len(all_metrics)} metrics saved")
    else:
        print("\n⚠ No metrics to save")

    # 古いファイルを圧縮
    archive_old_files()

    return 0

if __name__ == "__main__":
    exit(main())
