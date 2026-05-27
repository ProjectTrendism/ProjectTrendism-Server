from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, ForeignKey
from app.database import Base


class Season(Base):
    """
    시즌 상태 + 시즌별 트렌드.

    season.id가 곧 '몇 번째 시즌'인지를 의미한다 (id 1 = 1번째 시즌).
    사전 생성 스크립트가 미래 시즌들을 status="PENDING"으로 미리 만들어 두고,
    POST /explore/start가 PENDING 시즌을 하나씩 ACTIVE로 전환한다 (3-4에서 구현).
    """
    __tablename__ = "seasons"

    id           = Column(Integer, primary_key=True, index=True)
    current_day  = Column(Integer, default=1)        # 1~7
    current_time = Column(Integer, default=8)        # 8~22 (시간)
    phase        = Column(String, default="EXPLORE") # EXPLORE / CRAFT / SELL
    status       = Column(String, default="ACTIVE")  # PENDING / ACTIVE / FINISHED

    # -- 3번 신설: 시즌 트렌드 (AI가 사전 생성) --
    # 이번 시즌 트렌드 테마. 자유 텍스트. 공개 가능 (방향성 힌트).
    trend_theme        = Column(String, default="")
    # 이번 시즌 급상승 keyword_id 목록.
    # 서버 비밀 -- 플레이어는 NPC 대화로 추론해야 한다 (노출 정책은 3-4에서 확정).
    rising_keyword_ids = Column(JSON, default=list)


class NPC(Base):
    """
    NPC 마스터 데이터 (시즌 무관, 고정 정보).

    시즌마다 바뀌는 정보(대사/줄 키워드/신뢰도)는 SeasonNPCInfo로 분리됐다.
    """
    __tablename__ = "npcs"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    location    = Column(String, default="마을")
    portrait_id = Column(String, nullable=True)   # Unity 외형 매핑 키 (2026-05 신설)
    drop_rate   = Column(Float, default=0.7)      # 키워드 드랍 확률 (시즌 무관 기본값)
    is_active   = Column(Boolean, default=True)

    # -- 폴백 필드 (2026-05) --
    # SeasonNPCInfo가 아직 없을 때만(=3단계 AI 시즌 생성 전) 사용한다.
    # 시즌 시스템 안정화 후 제거 예정.
    dialogue      = Column(String, default="")    # 폴백 대사
    keyword_drops = Column(JSON, default=list)    # 폴백 키워드 풀 (keyword_id 목록)


class SeasonNPCInfo(Base):
    """
    시즌별 NPC 인스턴스 (2026-05 신설).

    같은 NPC라도 시즌마다 다른 대사/키워드/신뢰도를 갖는다.
    3단계(claude_service.generate_season_setup)에서 AI가 시즌 시작 시 채운다.
    (season_id, npc_id) 한 쌍당 한 레코드.
    """
    __tablename__ = "season_npc_info"

    id        = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), index=True)
    npc_id    = Column(Integer, ForeignKey("npcs.id"), index=True)

    # -- 공개 (클라이언트 노출 O) --
    season_dialogue = Column(String, default="")      # 이번 시즌 대사 (AI 생성)
    talked          = Column(Boolean, default=False)  # 이번 시즌 이 NPC와 대화했는지

    # -- 서버 비밀 (클라이언트 노출 X -- keyword r/g/b 숨김과 동일 원칙) --
    assigned_keywords = Column(JSON, default=list)     # 이번 시즌 이 NPC가 줄 keyword_id 목록
    true_reliability  = Column(Integer, default=60)    # 실제 신뢰도 0~100
    is_disinformer    = Column(Boolean, default=False) # 거짓 정보를 흘리는 NPC인지

    # -- 점진 공개용 --
    # 플레이어가 현재까지 추론한 신뢰도. 초기 None(미파악).
    # 대화/판매 결과로 갱신 (갱신 로직은 후속 단계에서 구현).
    perceived_reliability = Column(Integer, nullable=True)


class Event(Base):
    """이벤트 마스터 데이터"""
    __tablename__ = "events"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String, nullable=False)
    description     = Column(String, default="")
    event_type      = Column(String, default="RANDOM")  # FIXED / RANDOM
    trigger_day     = Column(Integer, nullable=True)     # 고정 이벤트 발생 일차
    trigger_prob    = Column(Float, default=0.3)         # 랜덤 이벤트 확률
    keyword_rewards = Column(JSON, default=list)         # 보상 keyword_id 목록
    is_active       = Column(Boolean, default=True)


class PlayerInventory(Base):
    """플레이어 보유 키워드"""
    __tablename__ = "player_inventory"

    id         = Column(Integer, primary_key=True, index=True)
    season_id  = Column(Integer, default=1)
    keyword_id = Column(Integer, ForeignKey("keywords.id"))
    quantity   = Column(Integer, default=1)