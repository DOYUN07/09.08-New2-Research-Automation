"""설정 파일 로딩."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class Institution:
    id: str
    name: str
    url: str = ""
    base: str = ""
    enabled: bool = True
    status: str = "check"
    type: str = "html"
    notes: str = ""
    verify_ssl: bool = True
    # 기관 사이트 밖으로 나가는 링크도 공고로 볼지 (기본: 버림)
    allow_external_links: bool = False
    encoding: str | None = None

    # 선택 오버라이드 — 비워두면 범용 파서가 알아서 처리
    row_selector: str | None = None
    title_selector: str | None = None
    date_selector: str | None = None
    deadline_selector: str | None = None
    link_from_onclick: str | None = None
    detail_url: str | None = None

    # JSON API 전용
    json_items: str | None = None
    json_title: str | None = None
    json_date: str | None = None
    json_id: str | None = None

    # 목록을 자바스크립트로 그리는 게시판은, 화면 주소 대신 그 화면이 실제로
    # 호출하는 주소를 직접 부른다. 그 주소가 POST만 받는 경우가 있다.
    #   method: "GET"(기본) 또는 "POST"
    #   post_data: "bsIdx=10002&menuId=822&pageIndex=1" 형태의 폼 데이터
    method: str = "GET"
    post_data: str | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "Institution":
        known = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in raw.items() if k in known}
        if not data.get("base"):
            data["base"] = data.get("url", "")
        return cls(**data)


@dataclass
class Config:
    recipients: list[str] = field(default_factory=list)
    subject_prefix: str = "[공고 브리핑]"
    sender_name: str = "공고 브리핑"

    lookback_days: int = 10
    max_per_institution: int = 5
    exclude_expired: bool = True
    unknown_deadline: str = "include_flagged"
    unknown_posted: str = "include"  # include | exclude
    dedupe: bool = True
    require_keyword: bool = True
    send_when_empty: bool = True

    # 마감일 확인 (상세 페이지 열어보기)
    verify_deadline: bool = True
    verify_max: int = 60
    verify_timeout: int = 15
    verify_delay: float = 0.4

    # 그날 공고만 담은 엑셀을 매일 메일에 첨부할지 (누적본과 같은 양식)
    daily_xlsx: bool = True

    # 누적 기록
    archive_enabled: bool = True
    # 저장소 엑셀을 갱신하고 메일에 첨부할 요일 (0=월 … 6=일). 기본 월·수·금
    archive_attach_weekdays: list[int] = field(default_factory=lambda: [0, 2, 4])
    # 예전 설정 이름(요일 하나). 남아 있으면 위 목록 대신 이걸 쓴다.
    archive_attach_weekday: int | None = None

    @property
    def archive_weekdays(self) -> list[int]:
        if self.archive_attach_weekday is not None:
            return [int(self.archive_attach_weekday)]
        return [int(x) for x in (self.archive_attach_weekdays or [])]

    def next_archive_day(self, today) -> str:
        """다음으로 저장소 엑셀이 갱신되는 요일 이름."""
        names = ["월", "화", "수", "목", "금", "토", "일"]
        days = sorted(self.archive_weekdays)
        if not days:
            return "설정된 요일 없음"
        for step in range(1, 8):
            wd = (today.weekday() + step) % 7
            if wd in days:
                return f"{names[wd]}요일"
        return "설정된 요일 없음"

    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)

    http: dict[str, Any] = field(default_factory=dict)
    sheet: dict[str, Any] = field(default_factory=dict)

    # 수신자를 어디서 읽었는지 (로그 표시용, 설정 파일에 쓰는 값이 아님)
    recipients_source: str = "config.yaml"

    @property
    def timeout(self) -> int:
        return int(self.http.get("timeout", 25))

    @property
    def retries(self) -> int:
        return int(self.http.get("retries", 2))

    @property
    def delay_between(self) -> float:
        return float(self.http.get("delay_between", 1.0))

    @property
    def user_agent(self) -> str:
        return self.http.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        )


def load_config(path: Path | None = None) -> Config:
    raw = _load_yaml(path or ROOT / "config.yaml")
    known = {f for f in Config.__dataclass_fields__}
    cfg = Config(**{k: v for k, v in raw.items() if k in known})

    # MAIL_TO 시크릿이 있으면 config.yaml 의 recipients 를 '대체'한다.
    # 이걸 모르면 config.yaml 에 주소를 추가해도 메일이 안 가서 한참 헤매게 되므로,
    # 어느 쪽을 썼는지 항상 로그에 남긴다.
    env_to = os.environ.get("MAIL_TO", "").strip()
    if env_to:
        cfg.recipients = [x.strip() for x in env_to.split(",") if x.strip()]
        cfg.recipients_source = "MAIL_TO 시크릿 (config.yaml 의 recipients 는 무시됨)"
    else:
        cfg.recipients_source = "config.yaml"
    return cfg


def load_institutions(path: Path | None = None) -> list[Institution]:
    raw = _load_yaml(path or ROOT / "institutions.yaml")
    return [Institution.from_dict(x) for x in raw.get("institutions", [])]
