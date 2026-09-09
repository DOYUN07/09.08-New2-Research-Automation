"""Gmail SMTP 발송.

앱 비밀번호는 코드에 절대 넣지 않습니다.
GitHub 저장소 → Settings → Secrets and variables → Actions 에서
  SMTP_USER      보내는 Gmail 주소
  SMTP_PASSWORD  Gmail 앱 비밀번호 16자리 (일반 비밀번호 아님)
두 개를 등록하면 그때부터 발송이 켜집니다. 등록 전에는 발송을 건너뛰고
결과를 파일(out/brief.html)로만 남깁니다.
"""
from __future__ import annotations

import os
import smtplib
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from pathlib import Path


class MailNotConfigured(Exception):
    """SMTP 자격증명이 아직 등록되지 않음 — 오류가 아니라 '아직 설정 전' 상태."""


def is_configured() -> bool:
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def clean_recipients(addrs: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """보낼 수 있는 주소만 남기고, 버린 주소는 이유와 함께 돌려준다.

    SMTP 는 수신자마다 'rcpt TO:<주소>' 라는 명령을 보내는데 이 명령은
    ASCII 로만 보낼 수 있다. 그래서 주소에 한글이 한 글자라도 있으면
    smtplib 이 UnicodeEncodeError 를 내고, 그 한 건 때문에 **정상 주소까지
    포함해 발송 전체가 실패한다.**

    실제로 config.yaml 에 예시 주소(받는사람1@example.com)를 지우지 않고
    실제 주소만 추가했을 때 이 일이 벌어졌다. 그래서 이제는 조용히 걸러낸다.
    """
    ok: list[str] = []
    dropped: list[tuple[str, str]] = []
    for raw in addrs:
        a = (raw or "").strip()
        if not a:
            continue
        if a in ok:
            continue
        try:
            a.encode("ascii")
        except UnicodeEncodeError:
            dropped.append((a, "주소에 한글 등 ASCII가 아닌 글자가 있음"))
            continue
        if a.count("@") != 1 or "." not in a.rsplit("@", 1)[-1] or " " in a:
            dropped.append((a, "이메일 형식이 아님"))
            continue
        if a.rsplit("@", 1)[-1].lower() in ("example.com", "example.org", "example.net"):
            dropped.append((a, "예시 주소"))
            continue
        ok.append(a)
    return ok, dropped


def send(
    subject: str,
    html_body: str,
    text_body: str,
    recipients: list[str],
    sender_name: str = "공고 브리핑",
    attachments: list[Path] | None = None,
) -> None:
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.environ.get("SMTP_PORT", "465"))

    if not user or not password:
        raise MailNotConfigured(
            "SMTP_USER / SMTP_PASSWORD 가 설정되지 않았습니다. "
            "GitHub Secrets에 등록하면 발송이 시작됩니다."
        )
    recipients, bad = clean_recipients(recipients)
    if not recipients:
        why = ("보낼 수 있는 주소가 없습니다 — " + ", ".join(f"{a}({r})" for a, r in bad)) if bad else (
            "수신자가 없습니다. config.yaml의 recipients 또는 MAIL_TO 시크릿을 확인하세요."
        )
        raise MailNotConfigured(why)

    body = MIMEMultipart("alternative")
    body.attach(MIMEText(text_body, "plain", "utf-8"))
    body.attach(MIMEText(html_body, "html", "utf-8"))

    files = [p for p in (attachments or []) if p and p.exists()]
    if files:
        msg = MIMEMultipart("mixed")
        msg.attach(body)
        for p in files:
            part = MIMEApplication(p.read_bytes(), _subtype="octet-stream")
            # 파일명이 한글이어도 깨지지 않도록 RFC 2231 형식으로 넣는다
            part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", p.name))
            msg.attach(part)
    else:
        msg = body

    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(sender_name, "utf-8")), user))
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=45) as smtp:
            smtp.login(user, password)
            smtp.sendmail(user, recipients, msg.as_bytes())
    else:
        with smtplib.SMTP(host, port, timeout=45) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(user, recipients, msg.as_bytes())
