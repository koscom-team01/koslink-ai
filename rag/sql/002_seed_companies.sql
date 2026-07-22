-- kosLINK AI RAG 파트 대상 기업 시드 데이터
-- 선행 조건: 001_create_tables.sql 실행 완료
--
-- corp_code(DART 8자리 고유번호)는 포함하지 않습니다 — 이 리스트엔 종목코드만
-- 있어서, shared/dart_client.resolve_corp_code(ticker)로 별도 조회해서 채워야
-- 합니다. 공시(disclosures) 수집 전에는 반드시 채워야 함 (companies.corp_code
-- 참고, 001_create_tables.sql 주석 참고).
--
-- 재실행해도 안전하도록 ticker 기준 ON CONFLICT DO NOTHING 사용.

INSERT INTO companies (ticker, name, role_code, role_name, size_tier) VALUES
    -- [R_CHIP] 칩 제조사
    ('005930', '삼성전자',       'R_CHIP', '칩 제조사', 'Large'),
    ('000660', 'SK하이닉스',      'R_CHIP', '칩 제조사', 'Large'),
    ('000990', 'DB하이텍',       'R_CHIP', '칩 제조사', 'Mid'),

    -- [R_IP] 반도체 IP 설계
    ('394280', '오픈엣지테크놀로지', 'R_IP', '반도체 IP 설계', 'Small'),
    ('094360', '칩스앤미디어',     'R_IP', '반도체 IP 설계', 'Small'),
    ('432720', '퀄리타스반도체',   'R_IP', '반도체 IP 설계', 'Small'),

    -- [R_DESIGN_HOUSE] 디자인하우스
    ('399720', '가온칩스',        'R_DESIGN_HOUSE', '디자인하우스', 'Small'),
    ('049080', '에이디테크놀로지', 'R_DESIGN_HOUSE', '디자인하우스', 'Small'),
    ('045970', '코아시아',        'R_DESIGN_HOUSE', '디자인하우스', 'Small'),

    -- [R_FABLESS] 팹리스
    ('108320', 'LX세미콘',        'R_FABLESS', '팹리스', 'Mid'),
    ('054450', '텔레칩스',        'R_FABLESS', '팹리스', 'Small'),
    ('396270', '넥스트칩',        'R_FABLESS', '팹리스', 'Small'),
    ('080220', '제주반도체',      'R_FABLESS', '팹리스', 'Small'),
    ('102950', '어보브반도체',    'R_FABLESS', '팹리스', 'Small'),

    -- [R_PKG_EQUIP] 패키징 장비
    ('042700', '한미반도체',      'R_PKG_EQUIP', '패키징 장비', 'Mid'),
    ('031980', '피에스케이홀딩스', 'R_PKG_EQUIP', '패키징 장비', 'Small'),
    ('039440', '에스티아이',      'R_PKG_EQUIP', '패키징 장비', 'Small'),
    ('110990', '디아이티',        'R_PKG_EQUIP', '패키징 장비', 'Small'),
    ('079370', '제우스',          'R_PKG_EQUIP', '패키징 장비', 'Small'),
    ('053610', '프로텍',          'R_PKG_EQUIP', '패키징 장비', 'Small'),
    ('412350', '레이저쎌',        'R_PKG_EQUIP', '패키징 장비', 'Small'),

    -- [R_TEST_EQUIP] 테스트 장비
    ('253590', '네오셈',          'R_TEST_EQUIP', '테스트 장비', 'Small'),
    ('232140', '와이씨',          'R_TEST_EQUIP', '테스트 장비', 'Small'),
    ('092870', '엑시콘',          'R_TEST_EQUIP', '테스트 장비', 'Small'),
    ('089030', '테크윙',          'R_TEST_EQUIP', '테스트 장비', 'Small'),
    ('003160', '디아이',          'R_TEST_EQUIP', '테스트 장비', 'Small'),
    ('322310', '오로스테크놀로지', 'R_TEST_EQUIP', '테스트 장비', 'Small'),
    ('348210', '넥스틴',          'R_TEST_EQUIP', '테스트 장비', 'Small'),
    ('064290', '인텍플러스',      'R_TEST_EQUIP', '테스트 장비', 'Small'),
    ('098460', '고영',            'R_TEST_EQUIP', '테스트 장비', 'Small'),

    -- [R_TEST_PART] 테스트 부품
    ('058470', '리노공업',        'R_TEST_PART', '테스트 부품', 'Mid'),
    ('095340', 'ISC',             'R_TEST_PART', '테스트 부품', 'Mid'),
    ('131290', '티에스이',        'R_TEST_PART', '테스트 부품', 'Small'),
    ('098120', '마이크로컨텍솔',  'R_TEST_PART', '테스트 부품', 'Small'),
    ('080580', '오킨스전자',      'R_TEST_PART', '테스트 부품', 'Small'),
    ('219130', '타이거일렉',      'R_TEST_PART', '테스트 부품', 'Small'),

    -- [R_EUV] 미세공정 EUV
    ('036810', '에프에스티',      'R_EUV', '미세공정 EUV', 'Small'),
    ('101490', '에스앤에스텍',    'R_EUV', '미세공정 EUV', 'Small'),
    ('403870', 'HPSP',            'R_EUV', '미세공정 EUV', 'Mid'),
    ('140860', '파크시스템스',    'R_EUV', '미세공정 EUV', 'Small'),

    -- [R_SUBSTRATE] 기판
    ('353200', '대덕전자',        'R_SUBSTRATE', '기판', 'Small'),
    ('222800', '심텍',            'R_SUBSTRATE', '기판', 'Small'),
    ('195870', '해성디에스',      'R_SUBSTRATE', '기판', 'Small'),
    ('007810', '코리아써키트',    'R_SUBSTRATE', '기판', 'Small'),

    -- [R_MATERIAL] 공정 소재
    ('005290', '동진쎄미켐',      'R_MATERIAL', '공정 소재', 'Mid'),
    ('357780', '솔브레인',        'R_MATERIAL', '공정 소재', 'Mid'),
    ('104830', '원익머트리얼즈',  'R_MATERIAL', '공정 소재', 'Small'),
    ('166090', '하나머티리얼즈',  'R_MATERIAL', '공정 소재', 'Small'),
    ('101160', '월덱스',          'R_MATERIAL', '공정 소재', 'Small'),
    ('064760', '티씨케이',        'R_MATERIAL', '공정 소재', 'Small'),
    ('319660', '피에스케이',      'R_MATERIAL', '공정 소재', 'Small')

ON CONFLICT (ticker) DO NOTHING;
