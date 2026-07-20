#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - RAG 파트 DB 연결 테스트 스크립트
connect_db.sh로 터널이 열려있는 상태에서 PostgreSQL(pgvector)과 Neo4j 접속이
정상적으로 되는지 빠르게 확인하기 위한 용도. rag/.env 값을 그대로 사용한다.

실행:
    cd rag
    python scripts/test_db_connection.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

PG_CONNECTION_STRING = os.environ.get(
    "PG_CONNECTION_STRING",
    "postgresql://admin:adminpassword@localhost:5432/koscomdb",
)
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4jpassword")


def test_postgres() -> bool:
    import psycopg

    # SQLAlchemy 스타일(postgresql+psycopg://) 접두어를 psycopg가 이해하는 형태로 변환
    dsn = PG_CONNECTION_STRING.replace("postgresql+psycopg://", "postgresql://")

    print("1) PostgreSQL(pgvector) 연결 테스트...")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()[0]
                print(f"   접속 성공: {version}")

                cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
                has_vector = cur.fetchone() is not None
                if has_vector:
                    print("   pgvector 익스텐션 확인됨")
                else:
                    print("   ⚠️ pgvector 익스텐션이 아직 설치되어 있지 않습니다 (vectordb/ 부트스트랩 필요).")
        return True
    except Exception as e:
        print(f"   ❌ 연결 실패: {e}")
        print("   connect_db.sh 터널이 켜져 있는지, localhost:5432가 열려있는지 확인하세요.")
        return False


def test_neo4j() -> bool:
    from neo4j import GraphDatabase

    print("2) Neo4j 연결 테스트...")
    driver = None
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        with driver.session() as session:
            count = session.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
            print(f"   접속 성공: 현재 그래프 노드 수 = {count}")
        return True
    except Exception as e:
        print(f"   ❌ 연결 실패: {e}")
        print("   connect_db.sh 터널이 켜져 있는지, localhost:7687가 열려있는지 확인하세요.")
        return False
    finally:
        if driver:
            driver.close()


if __name__ == "__main__":
    print("=" * 60)
    print("🔌 kosLINK AI RAG 파트 - DB 연결 테스트")
    print("=" * 60)

    pg_ok = test_postgres()
    print()
    neo4j_ok = test_neo4j()

    print("\n" + "=" * 60)
    if pg_ok and neo4j_ok:
        print("✅ 모든 DB 연결이 정상입니다.")
    else:
        print("⚠️ 일부 연결에 실패했습니다. 위 로그를 확인하세요.")
        sys.exit(1)
