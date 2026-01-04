#!/usr/bin/env python3
"""Send Telegram alerts for new encumbrance listings with AI verification"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import httpx
import anthropic
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
LOGGER = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
THREAD_ID = os.getenv('TELEGRAM_THREAD_ID')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

def get_db():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'realdb'),
        user=os.getenv('DB_USER', 'realuser'),
        password=os.getenv('DB_PASSWORD', 'strongpass123')
    )

def verify_encumbrance_with_ai(description: str, detected_types: list) -> dict:
    """Ask Claude to verify if this is a real encumbrance"""
    if not ANTHROPIC_API_KEY:
        LOGGER.warning("No Anthropic API key, skipping AI verification")
        return {"is_encumbrance": True, "reason": "AI verification skipped", "risk_level": "unknown"}
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    prompt = f"""Проанализируй описание квартиры и определи, есть ли ИНТЕРЕСНОЕ обременение.

Описание объявления:
{description}

Система обнаружила: {', '.join(detected_types) if detected_types else 'неизвестно'}

НЕ ИНТЕРЕСНО (пропускаем, is_encumbrance=false):
- Жильцы/арендаторы (просто квартиранты)
- "Снятие с регистрации до сделки" - выпишутся сами
- "Под залогом до [дата]" в контексте аванса/задатка покупателя
- Собственник прописан - это нормально
- "Не под арестом", "не в залоге" - отрицание обременения
- ПРАВО ПОЖИЗНЕННОГО ПРОЖИВАНИЯ - слишком проблемно!
- РЕНТА С ПОЖИЗНЕННЫМ СОДЕРЖАНИЕМ - слишком проблемно!
- Отказники от приватизации с пожизненным правом - не берём!

ИНТЕРЕСНЫЕ обременения (is_encumbrance=true):
- ИПОТЕКА / ЗАЛОГ БАНКА - любая! Это возможность для нашей услуги
- Несовершеннолетние прописаны (решается через опеку)
- Арест имущества (можно снять)
- Судебные споры по квартире (дисконт)
- Доли/совладельцы не согласны на продажу

Ответь в формате JSON:
{{
  "is_encumbrance": true/false,
  "risk_level": "high"/"medium"/"low"/"none",
  "encumbrance_type": "тип обременения или null",
  "reason": "краткое объяснение на русском (1-2 предложения)"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        import json
        result_text = response.content[0].text
        # Extract JSON from response
        if "{" in result_text and "}" in result_text:
            json_str = result_text[result_text.find("{"):result_text.rfind("}")+1]
            result = json.loads(json_str)
            LOGGER.info(f"AI verdict: {result}")
            return result
    except Exception as e:
        LOGGER.error(f"AI verification error: {e}")
    
    return {"is_encumbrance": True, "reason": "AI verification failed", "risk_level": "unknown"}

def send_telegram(message):
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    if THREAD_ID:
        payload["message_thread_id"] = int(THREAD_ID)
    
    response = httpx.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=payload,
        timeout=30
    )
    return response.status_code == 200

def main():
    conn = get_db()
    cur = conn.cursor()
    
    # Get new encumbrances from last 30 minutes that weren't sent yet
    cur.execute("""
        SELECT l.id, l.url, l.address, l.address_full, l.rooms, l.area_total, 
               l.floor, l.total_floors, l.encumbrance_types, l.description,
               lp.price
        FROM listings l
        JOIN LATERAL (
            SELECT price FROM listing_prices WHERE id = l.id ORDER BY seen_at DESC LIMIT 1
        ) lp ON true
        WHERE l.has_encumbrances = true 
          AND l.sent_to_tg = false
          AND l.first_seen_at > NOW() - INTERVAL '60 minutes'
        ORDER BY l.first_seen_at DESC
        LIMIT 10
    """)
    
    rows = cur.fetchall()
    sent = 0
    skipped = 0
    
    for row in rows:
        id_, url, address, address_full, rooms, area, floor, total_floors, enc_types, desc, price = row
        
        LOGGER.info(f"Checking listing {id_}...")
        
        # AI verification
        ai_result = verify_encumbrance_with_ai(desc or "", enc_types or [])
        
        if not ai_result.get("is_encumbrance", True):
            LOGGER.info(f"⏭️ Skipping {id_}: AI says not encumbrance - {ai_result.get('reason')}")
            # Mark as processed but not sent
            cur.execute("""
                UPDATE listings 
                SET has_encumbrances = false, 
                    is_error = false,
                    encumbrance_types = NULL
                WHERE id = %s
            """, (id_,))
            conn.commit()
            skipped += 1
            continue
        
        price_per_sqm = int(price / area) if area and area > 0 else 0
        rooms_str = f"{rooms}-комн" if rooms else "Студия"
        floor_str = f"{floor}/{total_floors}" if floor and total_floors else str(floor or "—")
        
        # Use AI's encumbrance type if available
        enc_str = ai_result.get("encumbrance_type") or (", ".join(enc_types) if enc_types else "обременение")
        risk_level = ai_result.get("risk_level", "medium")
        risk_label = {"high": "высокий", "medium": "средний", "low": "низкий"}.get(risk_level, "")

        # Short description
        desc_short = (desc[:200] + "...") if desc and len(desc) > 200 else (desc or "")
        ai_reason = ai_result.get("reason", "")

        message = f"""<b>Новый объект</b>

{address_full or address}
<b>{price:,.0f} ₽</b>  •  {price_per_sqm:,} ₽/м²
{area:.0f} м²  •  {rooms_str}  •  {floor_str} эт.

<b>{enc_str.upper()}</b>
<i>{ai_reason}</i>

{desc_short}

{url}"""

        if send_telegram(message):
            cur.execute("UPDATE listings SET sent_to_tg = true, sent_to_tg_at = NOW() WHERE id = %s", (id_,))
            conn.commit()
            sent += 1
            LOGGER.info(f"✅ Sent alert for {id_}")
    
    cur.close()
    conn.close()
    LOGGER.info(f"Done: {sent} alerts sent, {skipped} skipped by AI")

if __name__ == "__main__":
    main()
