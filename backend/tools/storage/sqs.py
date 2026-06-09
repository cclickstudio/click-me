"""SQS 메시지 큐 툴 — 시뮬레이션 비동기 태스크 enqueue / dequeue."""

import json

import aioboto3
from langchain_core.tools import tool

from core.config import settings

session = aioboto3.Session()


@tool
async def enqueue_simulation(job_id: str, ad_id: str, persona_count: int) -> str:
    """시뮬레이션 작업을 SQS 큐에 넣습니다.

    Returns:
        SQS MessageId
    """
    payload = {"job_id": job_id, "ad_id": ad_id, "persona_count": persona_count}
    async with session.client("sqs", region_name=settings.aws_region) as sqs:
        response = await sqs.send_message(
            QueueUrl=settings.sqs_simulation_queue_url,
            MessageBody=json.dumps(payload),
        )
    return response["MessageId"]


async def poll_simulation_queue() -> list[dict]:
    """SQS 큐에서 시뮬레이션 작업을 가져옵니다 (워커용, @tool 제외)."""
    async with session.client("sqs", region_name=settings.aws_region) as sqs:
        response = await sqs.receive_message(
            QueueUrl=settings.sqs_simulation_queue_url,
            MaxNumberOfMessages=settings.sqs_max_workers,
            WaitTimeSeconds=20,
        )
    return response.get("Messages", [])
