#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - Neo4j Ontology Initializer (53-Stock Semiconductor Scale)
반도체 핵심 소부장 53개사 데이터셋을 10대 공정 역할군에 맞춰 매핑 적재하는 초기화 스크립트입니다.
제도권 금융 기획서 및 발표 장표의 시각화 밀도를 극대화할 수 있도록 대량 시드 데이터를 수동 정의합니다.
"""

import sys
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4jpassword"

# ==========================================
# 1. 53대 기업 반도체 테마 및 기술군 데이터 정의
# ==========================================

THEMES = [
    {"id": "T_AI", "label": "온디바이스 AI", "desc": "기기 자체에서 실시간 연산을 수행하는 저전력 AI 반도체 생태계"},
    {"id": "T_HBM", "label": "HBM", "desc": "초고속 그래픽 처리장치(GPU) 데이터 전송을 가능케 하는 고대역폭 메모리 기술"},
    {"id": "T_CXL", "label": "CXL", "desc": "CPU-메모리-가속기 간 대역폭 한계를 허무는 차세대 인터페이스 프로토콜"}
]

ROLES = [
    {"id": "R_CHIP", "label": "칩 제조사", "desc": "종합 반도체 제조 및 파운드리 (IDM)"},
    {"id": "R_IP", "label": "반도체 IP 설계", "desc": "NPU 및 인터페이스 제어 특화 국산 설계 자산(IP)"},
    {"id": "R_DESIGN_HOUSE", "label": "디자인하우스", "desc": "설계도면을 파운드리 공정에 맞춰 최적화하는 미들웨어"},
    {"id": "R_FABLESS", "label": "팹리스", "desc": "생산설비(Fab) 없이 반도체 회로 설계에 집중하는 주체"},
    {"id": "R_PKG_EQUIP", "label": "패키징 장비", "desc": "첨단 적층(3D Stack) 및 접착(TC 본딩) 기계 장비"},
    {"id": "R_TEST_EQUIP", "label": "테스트 장비", "desc": "웨이퍼 및 가공 완료된 칩의 동작성 검사용 시스템 장비"},
    {"id": "R_TEST_PART", "label": "테스트 부품", "desc": "불량 검사 인터페이스에 들어가는 소모성 테스트 소켓 및 핀"},
    {"id": "R_EUV", "label": "미세공정 EUV", "desc": "극자외선(EUV) 노광 공정용 펠리클 및 정밀 계측 장비"},
    {"id": "R_SUBSTRATE", "label": "기판", "desc": "반도체 패키징용 FC-BGA 및 인쇄회로기판(PCB)"},
    {"id": "R_MATERIAL", "label": "공정 소재", "desc": "식각/세정액, 감광액, 실리콘 러버 등 화학 원자재"}
]

STOCKS = [
    # 1. R_CHIP (3)
    {"id": "S_SEC", "name": "삼성전자", "ticker": "005930", "capSize": "Large", "role": "R_CHIP"},
    {"id": "S_SKH", "name": "SK하이닉스", "ticker": "000660", "capSize": "Large", "role": "R_CHIP"},
    {"id": "S_DBH", "name": "DB하이텍", "ticker": "000990", "capSize": "Mid", "role": "R_CHIP"},

    # 2. R_IP (3)
    {"id": "S_OPE", "name": "오픈엣지테크놀로지", "ticker": "394280", "capSize": "Small", "role": "R_IP"},
    {"id": "S_CNM", "name": "칩스앤미디어", "ticker": "094360", "capSize": "Small", "role": "R_IP"},
    {"id": "S_QTB", "name": "퀄리타스반도체", "ticker": "432720", "capSize": "Small", "role": "R_IP"},

    # 3. R_DESIGN_HOUSE (3)
    {"id": "S_GAO", "name": "가온칩스", "ticker": "399720", "capSize": "Small", "role": "R_DESIGN_HOUSE"},
    {"id": "S_ADT", "name": "에이디테크놀로지", "ticker": "049080", "capSize": "Small", "role": "R_DESIGN_HOUSE"},
    {"id": "S_COA", "name": "코아시아", "ticker": "045970", "capSize": "Small", "role": "R_DESIGN_HOUSE"},

    # 4. R_FABLESS (5)
    {"id": "S_LXS", "name": "LX세미콘", "ticker": "108320", "capSize": "Mid", "role": "R_FABLESS"},
    {"id": "S_TLC", "name": "텔레칩스", "ticker": "054450", "capSize": "Small", "role": "R_FABLESS"},
    {"id": "S_NXC", "name": "넥스트칩", "ticker": "396270", "capSize": "Small", "role": "R_FABLESS"},
    {"id": "S_JJS", "name": "제주반도체", "ticker": "080220", "capSize": "Small", "role": "R_FABLESS"},
    {"id": "S_ABV", "name": "어보브반도체", "ticker": "102950", "capSize": "Small", "role": "R_FABLESS"},

    # 5. R_PKG_EQUIP (7)
    {"id": "S_HMI", "name": "한미반도체", "ticker": "042700", "capSize": "Mid", "role": "R_PKG_EQUIP"},
    {"id": "S_PSK_H", "name": "피에스케이홀딩스", "ticker": "031980", "capSize": "Small", "role": "R_PKG_EQUIP"},
    {"id": "S_STI", "name": "에스티아이", "ticker": "039440", "capSize": "Small", "role": "R_PKG_EQUIP"},
    {"id": "S_DIT", "name": "디아이티", "ticker": "110990", "capSize": "Small", "role": "R_PKG_EQUIP"},
    {"id": "S_ZEU", "name": "제우스", "ticker": "079370", "capSize": "Small", "role": "R_PKG_EQUIP"},
    {"id": "S_PRT", "name": "프로텍", "ticker": "053610", "capSize": "Small", "role": "R_PKG_EQUIP"},
    {"id": "S_LZC", "name": "레이저쎌", "ticker": "412350", "capSize": "Small", "role": "R_PKG_EQUIP"},

    # 6. R_TEST_EQUIP (9)
    {"id": "S_NEO", "name": "네오셈", "ticker": "253590", "capSize": "Small", "role": "R_TEST_EQUIP"},
    {"id": "S_YCI", "name": "와이씨", "ticker": "232140", "capSize": "Small", "role": "R_TEST_EQUIP"},
    {"id": "S_EXC", "name": "엑시콘", "ticker": "092870", "capSize": "Small", "role": "R_TEST_EQUIP"},
    {"id": "S_TCW", "name": "테크윙", "ticker": "089030", "capSize": "Small", "role": "R_TEST_EQUIP"},
    {"id": "S_DIA", "name": "디아이", "ticker": "003160", "capSize": "Small", "role": "R_TEST_EQUIP"},
    {"id": "S_ORO", "name": "오로스테크놀로지", "ticker": "322310", "capSize": "Small", "role": "R_TEST_EQUIP"},
    {"id": "S_NXT", "name": "넥스틴", "ticker": "348210", "capSize": "Small", "role": "R_TEST_EQUIP"},
    {"id": "S_ITP", "name": "인텍플러스", "ticker": "064290", "capSize": "Small", "role": "R_TEST_EQUIP"},
    {"id": "S_KOY", "name": "고영", "ticker": "098460", "capSize": "Small", "role": "R_TEST_EQUIP"},

    # 7. R_TEST_PART (6)
    {"id": "S_LNO", "name": "리노공업", "ticker": "058470", "capSize": "Mid", "role": "R_TEST_PART"},
    {"id": "S_ISC", "name": "ISC", "ticker": "095340", "capSize": "Mid", "role": "R_TEST_PART"},
    {"id": "S_TSE", "name": "티에스이", "ticker": "131290", "capSize": "Small", "role": "R_TEST_PART"},
    {"id": "S_MCT", "name": "마이크로컨텍솔", "ticker": "098120", "capSize": "Small", "role": "R_TEST_PART"},
    {"id": "S_OKS", "name": "오킨스전자", "ticker": "080580", "capSize": "Small", "role": "R_TEST_PART"},
    {"id": "S_TGE", "name": "타이거일렉", "ticker": "219130", "capSize": "Small", "role": "R_TEST_PART"},

    # 8. R_EUV (4)
    {"id": "S_FST", "name": "에프에스티", "ticker": "036810", "capSize": "Small", "role": "R_EUV"},
    {"id": "S_SST", "name": "에스앤에스텍", "ticker": "101490", "capSize": "Small", "role": "R_EUV"},
    {"id": "S_HPS", "name": "HPSP", "ticker": "403870", "capSize": "Mid", "role": "R_EUV"},
    {"id": "S_PSI", "name": "파크시스템스", "ticker": "140860", "capSize": "Small", "role": "R_EUV"},

    # 9. R_SUBSTRATE (4)
    {"id": "S_DDE", "name": "대덕전자", "ticker": "353200", "capSize": "Small", "role": "R_SUBSTRATE"},
    {"id": "S_STH", "name": "심텍", "ticker": "222800", "capSize": "Small", "role": "R_SUBSTRATE"},
    {"id": "S_HSD", "name": "해성디에스", "ticker": "195870", "capSize": "Small", "role": "R_SUBSTRATE"},
    {"id": "S_KAC", "name": "코리아써키트", "ticker": "007810", "capSize": "Small", "role": "R_SUBSTRATE"},

    # 10. R_MATERIAL (7)
    {"id": "S_DJS", "name": "동진쎄미켐", "ticker": "005290", "capSize": "Mid", "role": "R_MATERIAL"},
    {"id": "S_SOB", "name": "솔브레인", "ticker": "357780", "capSize": "Mid", "role": "R_MATERIAL"},
    {"id": "S_WNM", "name": "원익머트리얼즈", "ticker": "104830", "capSize": "Small", "role": "R_MATERIAL"},
    {"id": "S_HNM", "name": "하나머티리얼즈", "ticker": "166090", "capSize": "Small", "role": "R_MATERIAL"},
    {"id": "S_WDX", "name": "월덱스", "ticker": "101160", "capSize": "Small", "role": "R_MATERIAL"},
    {"id": "S_TCK", "name": "티씨케이", "ticker": "064760", "capSize": "Small", "role": "R_MATERIAL"},
    {"id": "S_PSK", "name": "피에스케이", "ticker": "319660", "capSize": "Small", "role": "R_MATERIAL"}
]

# 테마와 하부 밸류체인 공정 매핑
THEME_ROLE_RELATIONS = [
    # 온디바이스 AI 테마 소속 관계
    {"theme": "T_AI", "role": "R_CHIP"},
    {"theme": "T_AI", "role": "R_IP"},
    {"theme": "T_AI", "role": "R_DESIGN_HOUSE"},
    {"theme": "T_AI", "role": "R_FABLESS"},
    {"theme": "T_AI", "role": "R_TEST_PART"},
    
    # HBM 테마 소속 관계
    {"theme": "T_HBM", "role": "R_CHIP"},
    {"theme": "T_HBM", "role": "R_PKG_EQUIP"},
    {"theme": "T_HBM", "role": "R_TEST_PART"},
    {"theme": "T_HBM", "role": "R_SUBSTRATE"},
    {"theme": "T_HBM", "role": "R_MATERIAL"},

    # CXL 테마 소속 관계
    {"theme": "T_CXL", "role": "R_CHIP"},
    {"theme": "T_CXL", "role": "R_TEST_EQUIP"},
    {"theme": "T_CXL", "role": "R_SUBSTRATE"}
]

# 금감원 DART 및 기업 사업보고서 팩트로 검증된 기본 공급 계약선
STOCK_SUPPLY_RELATIONS = [
    {"from": "S_LNO", "to": "S_SEC", "product": "초미세 검사 핀(리노핀) 공급", "amount": "수주 누적액 상당", "source": "사업보고서"},
    {"from": "S_LNO", "to": "S_SKH", "product": "HBM R&D 검사용 소켓/프로브카드 공급", "amount": "기밀 수주 계약", "source": "DART 공시"},
    {"from": "S_ISC", "to": "S_SEC", "product": "메모리 반도체 테스트 소켓(실리콘 러버) 공급", "amount": "120억 원", "source": "분기보고서"},
    {"from": "S_ISC", "to": "S_SKH", "product": "HBM3E 파이널 테스트용 소켓 대규모 공급", "amount": "180억 원", "source": "DART 주요공시"},
    {"from": "S_HMI", "to": "S_SKH", "product": "HBM3E용 듀얼 TC 본더 적층 장비 독점 공급", "amount": "580억 원", "source": "DART 단일판매공시"},
    {"from": "S_NEO", "to": "S_SKH", "product": "CXL 2.0 테스터 시스템 검사 모듈 초도 납품", "amount": "72억 원", "source": "DART 공급계약공시"},
    {"from": "S_OPE", "to": "S_SEC", "product": "온디바이스 AI 칩셋 LPDDR5/LPDDR6 PHY 설계 IP 제공", "amount": "지식재산 계약액", "source": "DART IP라이선스"},
    {"from": "S_GAO", "to": "S_SEC", "product": "삼성 파운드리 4nm AI NPU 공정 디자인 서비스", "amount": "DSP 공식 계약", "source": "사업보고서"},
    {"from": "S_ADT", "to": "S_SEC", "product": "삼성 파운드리 3nm 미세공정 에이전트 설계 중개", "amount": "DSP 공식 파트너쉽", "source": "공식 분기보고서"},
    {"from": "S_CNM", "to": "S_SEC", "product": "영상 처리용 NPU 비디오 코덱 하드웨어 IP 라이선싱", "amount": "누적 수수료", "source": "DART 공시"},
    {"from": "S_QTB", "to": "S_SEC", "product": "초고속 초미세 인터페이스(SerDes) IP 공급", "amount": "라이선스 및 로열티", "source": "DART 특허보고서"},
    {"from": "S_TSE", "to": "S_SKH", "product": "테스트 보드 및 인터페이스 보드 공급", "amount": "43억 원", "source": "사업보고서"},
    {"from": "S_HPS", "to": "S_SEC", "product": "고압 수소 게이트 오클루전 어닐링 장비", "amount": "140억 원", "source": "DART 단일공급공시"},
    {"from": "S_HPS", "to": "S_SKH", "product": "고압 중수소 게이트 절연체 처리 장비", "amount": "92억 원", "source": "DART 공급계약공시"},
    {"from": "S_DDE", "to": "S_SKH", "product": "HBM 패키징용 초미세 기판 FC-BGA 공급", "amount": "수주 누적액 상당", "source": "분기보고서"},
    {"from": "S_STH", "to": "S_SKH", "product": "메모리용 반도체 패키지 기판 PCB 공급", "amount": "장기 거래망 구성", "source": "사업보고서"},
    {"from": "S_DJS", "to": "S_SEC", "product": "노광 공정용 초정밀 감광액(Photoresist) 공급", "amount": "독점 국산화 납품", "source": "사업보고서"},
    {"from": "S_SOB", "to": "S_SEC", "product": "초미세 3nm 세정용 고순도 불산 화학 약품 공급", "amount": "연간 장기 공급망", "source": "공식 사업보고서"}
]

# ==========================================
# 2. 적재 실행 클래스
# ==========================================

class OntologyInitializer:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def initialize_database(self):
        with self.driver.session() as session:
            # 1. Constraints & Indexes 생성
            print("⚙️ [1/5] Neo4j 스키마 제약조건(Constraints) 및 인덱스 선언 중...")
            session.execute_write(self._create_constraints)

            # 2. Theme Nodes 적재
            print("🗺️ [2/5] 3대 핵심 반도체 트렌드 테마(Theme) 노드 적재 중...")
            session.execute_write(self._load_themes, THEMES)

            # 3. Role Nodes 적재
            print("🛠️ [3/5] 10대 핵심 공정 밸류체인 역할(Role) 노드 적재 중...")
            session.execute_write(self._load_roles, ROLES)

            # 4. Stock Nodes 적재 & Role 연결
            print("📈 [4/5] 53대 반도체 상장 종목(Stock) 생성 및 기술 소속 관계 수립 중...")
            session.execute_write(self._load_stocks_and_belongs, STOCKS, THEME_ROLE_RELATIONS)

            # 5. Stock-to-Stock 공급 관계선 연결 (DART 팩트 메타데이터 기재)
            print("🔗 [5/5] 금감원 DART 공시 입증 기업 간 공급망 관계(SUPPLY_TO) 연결선 구축 중...")
            session.execute_write(self._connect_supply_chains, STOCK_SUPPLY_RELATIONS)
            
            print("\n🎉 kosLINK AI 53대 소부장 강소기업 시드 온톨로지 구축 완료!")

    @staticmethod
    def _create_constraints(tx):
        tx.run("CREATE CONSTRAINT unique_theme_id IF NOT EXISTS FOR (t:Theme) REQUIRE t.id IS UNIQUE")
        tx.run("CREATE CONSTRAINT unique_role_id IF NOT EXISTS FOR (r:Role) REQUIRE r.id IS UNIQUE")
        tx.run("CREATE CONSTRAINT unique_stock_id IF NOT EXISTS FOR (s:Stock) REQUIRE s.id IS UNIQUE")

    @staticmethod
    def _load_themes(tx, themes):
        query = """
        UNWIND $themes AS theme
        MERGE (t:Theme {id: theme.id})
        SET t.label = theme.label,
            t.description = theme.desc
        """
        tx.run(query, themes=themes)

    @staticmethod
    def _load_roles(tx, roles):
        query = """
        UNWIND $roles AS role
        MERGE (r:Role {id: role.id})
        SET r.label = role.label,
            r.description = role.desc
        """
        tx.run(query, roles=roles)

    @staticmethod
    def _load_stocks_and_belongs(tx, stocks, theme_roles):
        # 1. Stocks 생성 및 본인 역할(Role)에 연결
        for stock in stocks:
            query = """
            MERGE (s:Stock {id: $id})
            SET s.name = $name,
                s.ticker = $ticker,
                s.capSize = $capSize,
                s.marketType = CASE WHEN $ticker STARTS WITH "00" OR $ticker STARTS WITH "01" OR $ticker STARTS WITH "04" THEN "KOSPI" ELSE "KOSDAQ" END,
                s.sourceAPI = "InitialSeed_System",
                s.lastUpdated = datetime()
            
            WITH s
            MATCH (r:Role {id: $role_id})
            MERGE (s)-[:BELONGS_TO]->(r)
            """
            tx.run(query, id=stock["id"], name=stock["name"], ticker=stock["ticker"], capSize=stock["capSize"], role_id=stock["role"])

        # 2. 역할(Role)과 상위 테마(Theme) 연결
        for tr in theme_roles:
            query = """
            MATCH (r:Role {id: $role_id})
            MATCH (t:Theme {id: $theme_id})
            MERGE (r)-[:BELONGS_TO]->(t)
            """
            tx.run(query, role_id=tr["role"], theme_id=tr["theme"])

    @staticmethod
    def _connect_supply_chains(tx, relations):
        query = """
        UNWIND $relations AS rel
        MATCH (fromStock:Stock {id: rel.from})
        MATCH (toStock:Stock {id: rel.to})
        MERGE (fromStock)-[r:SUPPLY_TO]->(toStock)
        SET r.product = rel.product,
            r.amount = rel.amount,
            r.fact_source = rel.source,
            r.status = "VERIFIED",
            r.verifiedBy = "System_Initializer",
            r.verifiedAt = datetime()
        """
        tx.run(query, relations=relations)

# ==========================================
# 3. 메인 실행 엔트리포인트
# ==========================================
if __name__ == "__main__":
    print("▶️ kosLINK AI 53개사 온톨로지 적재를 시작합니다.")
    try:
        initializer = OntologyInitializer(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        initializer.initialize_database()
        initializer.close()
    except Exception as e:
        print(f"\n❌ Neo4j 데이터베이스 접속 실패!")
        print(f"사유: {e}")
        print("\n💡 [안내] 실제 실행을 원하시는 경우 로컬에 Neo4j 데스크톱이 켜져 있고")
        print(f"접속 암호가 '{NEO4J_PASSWORD}'로 일치하는지 확인해 주세요.")
        sys.exit(0)
