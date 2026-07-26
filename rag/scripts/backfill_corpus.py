#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - 사전학습 코퍼스(공시 + 과거 뉴스) 배치 임베딩 스크립트

disclosures / news_corpus 테이블에서 아직 임베딩 안 된(rag_embedded_at IS NULL)
행을 읽어와서 청킹 -> 프리픽스 조립 -> 임베딩(app/core/embeddings) -> pgvector(market_evidence
컬렉션) 저장까지 처리한다. 청킹/프리픽스/적재 로직은 app/utils/text_splitter.py,
app/services/ingestion_service.py로 옮겨서, 이 스크립트는 DB 조회 + 오케스트레이션
호출만 담당하는 얇은 CLI다(docs/rag_architecture.md 2장 폴더 구조 참고).

성공한 건마다 원본 테이블의 rag_embedded_at을 찍어 재실행해도 같은 문서가 중복
처리되지 않는다(멱등성). rag_ingestion_log에도 같이 기록해서 적재 이력을 남긴다
(rag_db_schema.md 1-6/2-1절 참고).

공시는 companies와 조인해서 ticker를 채우지만, news_corpus는 특정 기업 하나에
매인 데이터가 아니라 스키마 자체에 ticker 컬럼이 없다 - "관련주 찾기"는 별도
단계(실시간 분석 플로우)의 몫이라, 여기서는 ticker=None으로 남겨둔다.

실행:
    cd rag
    .venv/bin/python scripts/backfill_corpus.py --disclosures 3 --news 3
    .venv/bin/python scripts/backfill_corpus.py --disclosures 0 --news 0  # 전부 처리
"""

import argparse
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from langchain_postgres import PGVector

# rag/ 밑에 pyproject.toml/setup.py가 없어서 `app` 패키지가 pip install되어 있지
# 않다 - cwd(rag/)가 아니라 이 파일 위치 기준으로 rag/를 sys.path에 넣어야
# PYTHONPATH 지정 없이도 어디서 실행하든 `from app...` import가 된다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.core.embeddings.factory import get_embedding_provider  # noqa: E402
from app.services.ingestion_service import chunk_and_store  # noqa: E402
from app.utils.text_splitter import build_prefix

load_dotenv()

settings = get_settings()
PG_CONNECTION_STRING = settings.PG_CONNECTION_STRING


def fetch_pending_disclosures(conn: psycopg.Connection, limit: int | None) -> list[dict]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            f"""
            SELECT d.rcept_no, d.report_nm, d.rcept_dt, d.raw_text, d.source_url,
                   c.ticker, c.name AS company_name
            FROM disclosures d
            JOIN companies c ON c.corp_code = d.corp_code
            WHERE d.rag_embedded_at IS NULL
            ORDER BY length(d.raw_text)
            {"LIMIT %s" if limit else ""}
            """,
            (limit,) if limit else (),
        )
        return cur.fetchall()


def fetch_pending_news(conn: psycopg.Connection, limit: int | None) -> list[dict]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            f"""
            SELECT news_corpus_id AS news_id, title, body, press, url, published_at
            FROM news_corpus
            WHERE rag_embedded_at IS NULL
            ORDER BY length(body)
            {"LIMIT %s" if limit else ""}
            """,
            (limit,) if limit else (),
        )
        return cur.fetchall()


def mark_ingested(
    conn: psycopg.Connection,
    *,
    table: str,
    id_column: str,
    doc_id,
    log_source_type: str,
    ticker: str | None,
    chunk_count: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET rag_embedded_at = now() WHERE {id_column} = %s",
            (doc_id,),
        )
        cur.execute(
            """
            INSERT INTO rag_ingestion_log (source_type, source_doc_id, ticker, chunk_count)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_type, source_doc_id) DO UPDATE
                SET chunk_count = EXCLUDED.chunk_count, ingested_at = now()
            """,
            (log_source_type, str(doc_id), ticker, chunk_count),
        )
    conn.commit()


def process_disclosures(conn, vector_store, limit: int | None) -> None:
    rows = fetch_pending_disclosures(conn, limit)
    print(f"[공시] 처리 대상: {len(rows)}건", flush=True)
    for row in rows:
        try:
            prefix = build_prefix(row["company_name"], row["report_nm"])
            metadata = {
                "ticker": row["ticker"],
                "source_type": "disclosure",
                "source_doc_id": row["rcept_no"],
                "title": row["report_nm"],
                "url": row["source_url"],
                "published_date": str(row["rcept_dt"]) if row["rcept_dt"] else None,
            }
            chunk_count = chunk_and_store([(prefix, row["raw_text"], metadata)], vector_store)
            mark_ingested(
                conn,
                table="disclosures",
                id_column="rcept_no",
                doc_id=row["rcept_no"],
                log_source_type="disclosure",
                ticker=row["ticker"],
                chunk_count=chunk_count,
            )
            print(f"  [완료] {row['rcept_no']} ({row['company_name']}) - {chunk_count}개 청크", flush=True)
        except Exception as e:  # noqa: BLE001 - 배치라 한 건 실패로 전체가 멎으면 안 됨
            conn.rollback()
            print(f"  [실패] {row['rcept_no']} ({row['company_name']}) - {e}", flush=True)


def process_news(conn, vector_store, limit: int | None) -> None:
    rows = fetch_pending_news(conn, limit)
    print(f"[뉴스] 처리 대상: {len(rows)}건", flush=True)
    for row in rows:
        try:
            prefix = build_prefix(row["title"])
            metadata = {
                "ticker": None,
                "source_type": "news",
                "source_doc_id": str(row["news_id"]),
                "title": row["title"],
                "url": row["url"],
                "published_date": str(row["published_at"]) if row["published_at"] else None,
            }
            chunk_count = chunk_and_store([(prefix, row["body"], metadata)], vector_store)
            mark_ingested(
                conn,
                table="news_corpus",
                id_column="news_corpus_id",
                doc_id=row["news_id"],
                log_source_type="news_backfill",
                ticker=None,
                chunk_count=chunk_count,
            )
            print(f"  [완료] news_id={row['news_id']} ({row['press']}) - {chunk_count}개 청크", flush=True)
        except Exception as e:  # noqa: BLE001 - 배치라 한 건 실패로 전체가 멎으면 안 됨
            conn.rollback()
            print(f"  [실패] news_id={row['news_id']} - {e}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="공시/과거뉴스 배치 임베딩")
    parser.add_argument("--disclosures", type=int, default=3, help="공시 처리 건수 (0=전부)")
    parser.add_argument("--news", type=int, default=3, help="과거뉴스 처리 건수 (0=전부)")
    args = parser.parse_args()

    disclosures_limit = None if args.disclosures == 0 else args.disclosures
    news_limit = None if args.news == 0 else args.news

    vector_store = PGVector(
        embeddings=get_embedding_provider(),
        collection_name=settings.VECTOR_COLLECTION_NAME,
        connection=PG_CONNECTION_STRING,
    )

    dsn = PG_CONNECTION_STRING.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as conn:
        process_disclosures(conn, vector_store, disclosures_limit)
        process_news(conn, vector_store, news_limit)

    print("배치 임베딩 완료", flush=True)


if __name__ == "__main__":
    main()
