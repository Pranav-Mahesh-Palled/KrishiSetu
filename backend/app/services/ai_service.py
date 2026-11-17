"""Gemini AI Advisory & Multilingual Q&A Service for KrishiSetu.

Provides:
- Grounded structured advisory cards via Google GenAI SDK (gemini-3.5-flash-lite)
- Conversational regional Q&A (generate_chat_reply)
- Deterministic multilingual template fallback (EN, KN, HI, MR) for resilient offline operation
"""

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

GEMINI_PRIMARY_MODEL = "gemini-3.5-flash-lite"

# Structured Pydantic schema for Gemini JSON output
class AIAdvisory(BaseModel):
    headline: str = Field(description="Crisp 1-line verdict for the farmer")
    harvest_action: str = Field(description="Actionable advice on harvest timing based on weather")
    recommended_mandi: str = Field(description="Exact name of the highest net profit mandi")
    price_justification: str = Field(description="Clear breakdown explaining net profit after transport and spoilage")
    protection_tips: List[str] = Field(description="2-3 specific post-harvest protection precautions")
    language: str = Field(description="Language code: en, kn, hi, or mr")


def _is_valid_api_key(key: Optional[str]) -> bool:
    """Checks whether an actual Gemini API key is configured."""
    if not key:
        return False
    clean = key.strip()
    return len(clean) > 20 and not clean.startswith("your_")


def build_template_advisory(
    crop_info: Dict[str, Any],
    weather_info: Dict[str, Any],
    mandi_comparison: List[Dict[str, Any]],
    quantity: float,
    language: str = "en",
    price_comparison_status: str = "verified_comparison_available",
) -> AIAdvisory:
    """Generates a grounded, localized advisory using deterministic templates."""
    lang = (language or "en").lower().strip()
    if lang not in ["en", "kn", "hi", "mr"]:
        lang = "en"

    crop_en = crop_info.get("display_name_en", "Crop")
    crop_kn = crop_info.get("display_name_kn", crop_en)
    crop_hi = crop_info.get("display_name_hi", crop_en)
    crop_mr = crop_info.get("display_name_mr", crop_en)

    risk_level = weather_info.get("risk_level", "SAFE_WINDOW")
    rain_72h = weather_info.get("rain_72h_mm", 0.0)
    rain_prob = weather_info.get("max_rain_prob_pct", 0.0)

    # 1. Location outside 150 km coverage area
    if not mandi_comparison:
        if lang == "kn":
            return AIAdvisory(
                headline="150 ಕಿ.ಮೀ ವ್ಯಾಪ್ತಿಯಲ್ಲಿ ಬೆಂಬಲಿತ ಎಪಿಎಂಸಿ ಮಾರುಕಟ್ಟೆಗಳು ಲಭ್ಯವಿಲ್ಲ",
                harvest_action="ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ ಗಮನಿಸಿ ಸ್ಥಳೀಯವಾಗಿ ಕೊಯ್ಲು ಕೈಗೊಳ್ಳಿ.",
                recommended_mandi="ಸ್ಥಳೀಯ ಮಾರುಕಟ್ಟೆ / ನೇರ ವ್ಯಾಪಾರ",
                price_justification="ನಿಮ್ಮ ಸ್ಥಳವು ಪ್ರಸ್ತುತ ಲಭ್ಯವಿರುವ 150 ಕಿ.ಮೀ ಎಪಿಎಂಸಿ ವ್ಯಾಪ್ತಿಯ ಹೊರಗಿದೆ (ಕರ್ನಾಟಕ ಮತ್ತು ಮಹಾರಾಷ್ಟ್ರ ಮಾರುಕಟ್ಟೆಗಳಿಗೆ ಸೀಮಿತ). ದಯವಿಟ್ಟು ಸ್ಥಳೀಯ ವರ್ತಕರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
                protection_tips=[
                    f"ಸ್ಥಳೀಯ ಗೋದಾಮಿನಲ್ಲಿ {crop_kn} ಒಣಗಿಸಿ ಸುರಕ್ಷಿತವಾಗಿಡಿ.",
                    "ಮಳೆ ಬರುವ ಮುನ್ನ ಸೂಕ್ತ ಟಾರ್ಪಲಿನ್ ವ್ಯವಸ್ಥೆ ಮಾಡಿಕೊಳ್ಳಿ.",
                ],
                language="kn",
            )
        elif lang == "hi":
            return AIAdvisory(
                headline="150 किमी के दायरे में कोई समर्थित एपीएमसी मंडी उपलब्ध नहीं है",
                harvest_action="मौसम के पूर्वानुमान को देखते हुए स्थानीय स्तर पर कटाई और भंडारण करें।",
                recommended_mandi="स्थानीय व्यापारी / उप-मंडी",
                price_justification="आपका स्थान वर्तमान 150 किमी कवरेज क्षेत्र से बाहर है (कर्नाटक और महाराष्ट्र क्लस्टर)। कृपया स्थानीय बाजार में दरें पता करें।",
                protection_tips=[
                    f"{crop_hi} को खुले में छोड़ने के बजाय सुरक्षित शेड या गोदाम में रखें।",
                    "संभावित बारिश से बचाव के लिए तिरपाल तैयार रखें।",
                ],
                language="hi",
            )
        elif lang == "mr":
            return AIAdvisory(
                headline="150 किमी परिसरात कोणतीही समर्थित कृषी उत्पन्न बाजार समिती उपलब्ध नाही",
                harvest_action="हवामान अंदाज लक्षात घेऊन स्थानिक पातळीवर काढणीचे नियोजन करा.",
                recommended_mandi="स्थानिक बाजार / थेट खरेदीदार",
                price_justification="आपले स्थान सध्याच्या 150 किमी कार्यक्षेत्राबाहेर आहे (महाराष्ट्र व कर्नाटक सीमावर्ती भाग). कृपया स्थानिक व्यापाऱ्यांशी संपर्क साधावा.",
                protection_tips=[
                    f"{crop_mr} कोरड्या जागी सुरक्षित साठवून ठेवा.",
                    "पावसाची शक्यता असल्यास तातडीने ताडपत्री आच्छादन करा.",
                ],
                language="mr",
            )
        else:
            return AIAdvisory(
                headline="No Supported APMC Mandis Found within 150 km Radius",
                harvest_action="Plan harvest according to local weather indicators and secure adequate storage.",
                recommended_mandi="Local Village Market / Direct Buyer",
                price_justification="Your origin is outside KrishiSetu's current 150 km APMC coverage zone (optimized for Karnataka and Maharashtra). Please check quotations with local traders or regional state mandis.",
                protection_tips=[
                    f"Store harvested {crop_en} in well-aerated dry storage facilities.",
                    "Keep waterproof tarpaulins ready in case of unexpected rain.",
                ],
                language="en",
            )

    local_mandi = next((m for m in mandi_comparison if m.get("is_local")), mandi_comparison[0])
    local_name = local_mandi.get("market", "Local APMC")
    local_modal = local_mandi.get("modal_price", 2000.0)
    local_net = local_mandi.get("net_price_per_qtl", local_modal)

    # 2. No verified price data at all across nearby mandis (e.g. Haveri Maize)
    if price_comparison_status == "no_verified_price_data" or all(m.get("is_benchmark") for m in mandi_comparison):
        if lang == "kn":
            return AIAdvisory(
                headline=f"{crop_kn} ಬೆಳೆಗೆ ದೃಢೀಕೃತ ಎಪಿಎಂಸಿ ದರಗಳು ಲಭ್ಯವಿಲ್ಲ — ಸ್ಥಳೀಯ ಹರಾಜು ಪರಿಶೀಲಿಸಿ",
                harvest_action="ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ ಗಮನಿಸಿ ಕೊಯ್ಲು ಕೈಗೊಳ್ಳಿ ಹಾಗೂ ಸ್ಥಳೀಯ ಎಪಿಎಂಸಿಯಲ್ಲಿ ಪ್ರಸ್ತುತ ದರ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.",
                recommended_mandi=f"{local_name} (ದೃಢೀಕೃತ ದತ್ತಾಂಶ ಕೊರತೆ — ಸ್ಥಳೀಯ ಮಾರಾಟ ಸೂಕ್ತ)",
                price_justification=f"ಸಮೀಪದ ಯಾವುದೇ ಎಪಿಎಂಸಿಯಲ್ಲಿ {crop_kn} ಬೆಳೆಗೆ ಇಂದಿನ ಅಧಿಕೃತ ಸರ್ಕಾರಿ AGMARKNET ಹರಾಜು ದರಗಳು ದಾಖಲಾಗಿಲ್ಲ. ಪಟ್ಟಿಯಲ್ಲಿ ತೋರಿಸಲಾದ ದರಗಳು ಅಂದಾಜು ಮಾನದಂಡಗಳಾಗಿದ್ದು, ಇವುಗಳ ಆಧಾರದ ಮೇಲೆ ಯಾವುದೇ ಮಾರುಕಟ್ಟೆ ಶ್ರೇಷ್ಠತೆಯನ್ನಾಗಲೀ ಅಥವಾ ನಿವ್ವಳ ಲಾಭದ ಖಾತರಿಯನ್ನಾಗಲೀ ನೀಡಲು ಸಾಧ್ಯವಿಲ್ಲ.",
                protection_tips=[
                    f"ದೃಢೀಕೃತ ದರ ಬರುವವರೆಗೆ {crop_kn} ಅನ್ನು ಒಣ, ಗಾಳಿಯಾಡುವ ಗೋದಾಮಿನಲ್ಲಿ ಸುರಕ್ಷಿತವಾಗಿಡಿ.",
                    "ಸ್ಥಳೀಯ ಮಂಡಿ ಕಮಿಷನ್ ಏಜೆಂಟರನ್ನು ಸಂಪರ್ಕಿಸಿ ಇಂದಿನ ಪ್ರಸ್ತುತ ನೇರ ಹರಾಜು ದರ ತಿಳಿಯಿರಿ.",
                ],
                language="kn",
            )
        elif lang == "hi":
            return AIAdvisory(
                headline=f"{crop_hi} के लिए आज आधिकारिक सरकारी नीलामी भाव उपलब्ध नहीं हैं",
                harvest_action="मौसम के पूर्वानुमान अनुसार कटाई करें तथा स्थानीय मंडी में वर्तमान बोली भाव पता करें।",
                recommended_mandi=f"{local_name} (सत्यापित डेटा अपर्याप्त — स्थानीय स्तर पर बेचें)",
                price_justification=f"निकटवर्ती किसी भी मंडी में {crop_hi} के लिए आज के आधिकारिक AGMARKNET आवक भाव दर्ज नहीं हैं। प्रदर्शित आंकड़े केवल अनुमानित बेंचमार्क हैं। इनके आधार पर किसी अन्य दूरस्थ मंडी को बेहतर नहीं माना जा सकता और न ही अतिरिक्त लाभ का दावा किया जा सकता है।",
                protection_tips=[
                    f"{crop_hi} को सुरक्षित गोदाम में रखें ताकि गुणवत्ता खराब न हो।",
                    "सटीक भाव के लिए स्थानीय मंडी समिति सचिव या आढ़ती से सीधा संपर्क करें।",
                ],
                language="hi",
            )
        elif lang == "mr":
            return AIAdvisory(
                headline=f"{crop_mr} पिकासाठी आजचे अधिकृत बाजार समिती भाव उपलब्ध नाहीत",
                harvest_action="हवामान अंदाज पाहून काढणी करा व स्थानिक बाजारात थेट बोली तपासा.",
                recommended_mandi=f"{local_name} (माहिती अपुरी — स्थानिक बाजारात विक्री योग्य)",
                price_justification=f"परिसरातील कोणत्याही बाजार समितीत {crop_mr} साठी आजचे सत्यापित AGMARKNET दर नोंदवलेले नाहीत. दाखवलेले भाव केवळ संदर्भ बेंचमार्क असून त्यावर कोणतीही दूरची बाजार समिती अधिक नफ्याची म्हणून शिफारस केली जाऊ शकत नाही.",
                protection_tips=[
                    f"{crop_mr} योग्य प्रकारे वाळवून कोरड्या जागेत साठवा.",
                    "स्थानिक बाजार समितीच्या आड़त्यांशी संपर्क साधून प्रत्यक्ष बोली भाव तपासा.",
                ],
                language="mr",
            )
        else:
            return AIAdvisory(
                headline=f"Insufficient Verified Price Data for {crop_en}",
                harvest_action="Plan harvest per weather windows and verify real-time physical bids at your local APMC yard.",
                recommended_mandi=f"{local_name} (Verified Data Insufficient — Prioritize Local Market)",
                price_justification=f"No verified government AGMARKNET auction quotations were recorded for {crop_en} across nearby mandis today. Values shown are unverified estimated benchmarks and cannot be used to establish authoritative mandi recommendations or verified arbitrage profits.",
                protection_tips=[
                    f"Store harvested {crop_en} in dry, well-ventilated storage until official arrivals resume.",
                    "Contact local APMC commission agents directly to ascertain physical spot auction rates.",
                ],
                language="en",
            )

    # 3. Local baseline missing/unverified, but alternative mandis have verified live quotes (e.g. Kolar Tomato, Nashik Onion)
    if price_comparison_status == "local_baseline_missing":
        alt_reporting = [m.get("market") for m in mandi_comparison if not m.get("is_local") and not m.get("is_benchmark")]
        alt_names = ", ".join(alt_reporting[:2]) if alt_reporting else "regional mandis"

        if lang == "kn":
            return AIAdvisory(
                headline=f"{crop_kn} ಬೆಳೆಗೆ ಸ್ಥಳೀಯ ಮೂಲ ದರ ಲಭ್ಯವಿಲ್ಲ — ಪ್ರಾದೇಶಿಕ ದರಗಳು ಕೇವಲ ಮಾಹಿತಿಗೆ",
                harvest_action=f"ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ ಗಮನಿಸಿ ಕೊಯ್ಲು ಮಾಡಿ ಹಾಗೂ ವಾಹನ ಸಾಗಾಟದ ಮುನ್ನ {local_name} ಮಂಡಿಯಲ್ಲಿ ಇಂದಿನ ನೇರ ಹರಾಜು ದರ ಪರಿಶೀಲಿಸಿ.",
                recommended_mandi=f"{local_name} (ಸ್ಥಳೀಯ ಮಂಡಿ ದರ ಮೊದಲು ಪರಿಶೀಲಿಸಿ)",
                price_justification=f"ಪ್ರಾದೇಶಿಕ ಮಾರುಕಟ್ಟೆಗಳಲ್ಲಿ ({alt_names}) ಇಂದಿನ ಅಧಿಕೃತ AGMARKNET ದರಗಳು ಲಭ್ಯವಿದ್ದರೂ, ನಿಮ್ಮ ಸ್ಥಳೀಯ {local_name} ಮಂಡಿಯಲ್ಲಿ ಇಂದಿನ ಆಗಮನ ದರ ದಾಖಲಾಗಿಲ್ಲ. ಸ್ಥಳೀಯ ಮೂಲ ದರದ ಕೊರತೆಯಿಂದ ನಿವ್ವಳ ಲಾಭದ ಲೆಕ್ಕಾಚಾರ ಅಸಾಧ್ಯ. ಪ್ರಾದೇಶಿಕ ದರಗಳನ್ನು ಕೇವಲ ಉಲ್ಲೇಖಕ್ಕಾಗಿ ತೋರಿಸಲಾಗಿದೆ.",
                protection_tips=[
                    f"ಸಾಗಾಟಕ್ಕೂ ಮುನ್ನ {local_name} ದಲ್ಲಾಳಿಗಳನ್ನು ಸಂಪರ್ಕಿಸಿ ಸ್ಥಳೀಯ ಹರಾಜು ದರ ತಿಳಿಯಿರಿ.",
                    "ಸ್ಥಳೀಯ ದರವು ಪ್ರಾದೇಶಿಕ ದರಕ್ಕಿಂತ ಗಮನಾರ್ಹವಾಗಿ ಕಡಿಮೆಯಿದ್ದರೆ ಮಾತ್ರ ಸಾಗಾಟ ಪರಿಗಣಿಸಿ.",
                ],
                language="kn",
            )
        elif lang == "hi":
            return AIAdvisory(
                headline=f"{crop_hi} के लिए स्थानीय आधार मूल्य अनुपलब्ध — क्षेत्रीय भाव केवल संदर्भ हेतु",
                harvest_action=f"मौसम अनुसार कटाई करें तथा परिवहन से पहले {local_name} मंडी में वर्तमान बोली भाव की पुष्टि करें।",
                recommended_mandi=f"{local_name} (स्थानीय बोली पहले जांचें)",
                price_justification=f"निकटवर्ती मंडियों ({alt_names}) में आज के आधिकारिक आवक भाव उपलब्ध हैं, परंतु आपकी स्थानीय {local_name} मंडी का आधिकारिक भाव आज दर्ज नहीं हुआ है। स्थानीय आधार मूल्य के बिना अतिरिक्त शुद्ध लाभ का दावा नहीं किया जा सकता।",
                protection_tips=[
                    f"वाहन बुक करने से पहले {local_name} में वर्तमान हाजिर भाव पता करें।",
                    "यदि स्थानीय भाव बहुत कम हों, तभी अन्य दूरस्थ मंडियों में माल भेजने का निर्णय लें।",
                ],
                language="hi",
            )
        elif lang == "mr":
            return AIAdvisory(
                headline=f"{crop_mr} पिकासाठी स्थानिक आधारभूत भाव उपलब्ध नाही — प्रादेशिक दर केवळ संदर्भासाठी",
                harvest_action=f"हवामान अंदाज पाहून काढणी करा व वाहतुकीपूर्वी {local_name} बाजार समितीत प्रत्यक्ष बोली तपासा.",
                recommended_mandi=f"{local_name} (स्थानिक प्रत्यक्ष दर आधी तपासा)",
                price_justification=f"परिसरातील इतर बाजार समित्यांचे ({alt_names}) आजचे अधिकृत दर उपलब्ध असले, तरी आपल्या स्थानिक {local_name} बाजाराचे अधिकृत आवक दर नोंदवले गेलेले नाहीत. स्थानिक आधार दराशिवाय अतिरिक्त नफ्याची खात्री देता येत नाही.",
                protection_tips=[
                    f"वाहतूक करण्यापूर्वी {local_name} बाजारातील प्रत्यक्ष बोली तपासा.",
                    "स्थानिक दर अत्यंत कमी असल्यासच इतर बाजार समित्यांचा विचार करावा.",
                ],
                language="mr",
            )
        else:
            return AIAdvisory(
                headline=f"Local Baseline Price Missing for {crop_en} — Regional Quotes Shown for Reference",
                harvest_action=f"Plan harvest per weather indicators and verify physical spot auction bids at {local_name} before arranging transport.",
                recommended_mandi=f"{local_name} (Verify Local Spot Auction Rate)",
                price_justification=f"Official live AGMARKNET quotations were recorded today in regional markets ({alt_names}), but your local baseline market ({local_name}) has not filed an official arrival return today. Because the local baseline is unverified, net arbitrage gains cannot be established. Regional quotes are displayed for reference only; farmers should verify local spot auction rates before travelling.",
                protection_tips=[
                    f"Contact local commission agents at {local_name} to ascertain physical spot prices before booking transport.",
                    "Only consider distant transport if verified regional spreads substantially exceed transport and transit spoilage costs.",
                ],
                language="en",
            )

    # 4. Local baseline verified, but alternative mandis lack verified quotes (e.g. Pune Potato)
    if price_comparison_status == "insufficient_alternative_quotes":
        if lang == "kn":
            return AIAdvisory(
                headline=f"{crop_kn} ಬೆಳೆಗೆ ಸ್ಥಳೀಯ ದೃಢೀಕೃತ ದರ ಲಭ್ಯ — ಸ್ಥಳೀಯ ಮಂಡಿಯಲ್ಲೇ ಮಾರಾಟ ಸೂಕ್ತ",
                harvest_action=f"ನಿಮ್ಮ ಸ್ಥಳೀಯ {local_name} ಎಪಿಎಂಸಿಯಲ್ಲಿ ಇಂದಿನ ದೃಢೀಕೃತ ದರದಲ್ಲಿ ಮಾರಾಟ ಕೈಗೊಳ್ಳಿ.",
                recommended_mandi=f"{local_name} (ದೃಢೀಕೃತ ಸ್ಥಳೀಯ ಮಾರಾಟ ಸೂಕ್ತ)",
                price_justification=f"ನಿಮ್ಮ ಸ್ಥಳೀಯ {local_name} ಮಂಡಿಯಲ್ಲಿ ಇಂದಿನ ಅಧಿಕೃತ ಸರ್ಕಾರಿ ದರ ಕ್ವಿಂಟಾಲ್‌ಗೆ ₹{local_modal:,.0f} ಆಗಿದೆ (ನಿವ್ವಳ ₹{local_net:,.0f}). ನೆರೆಯ ಪರ್ಯಾಯ ಮಾರುಕಟ್ಟೆಗಳಲ್ಲಿ ಇಂದಿನ ದೃಢೀಕೃತ ದರಗಳು ದಾಖಲಾಗಿಲ್ಲ. ಅಂದಾಜು ಬೆಲೆಗಳ ಆಧಾರದ ಮೇಲೆ ದೂರದ ಮಾರುಕಟ್ಟೆಗಳಿಗೆ ಸಾಗಿಸುವುದು ಸೂಕ್ತವಲ್ಲ.",
                protection_tips=[
                    f"{crop_kn} ಅನ್ನು ಸ್ಥಳೀಯ {local_name} ಮಂಡಿಗೆ ತಂಪಾದ ಮುಂಜಾನೆಯ ವೇಳೆಯಲ್ಲಿ ತಲುಪಿಸಿ.",
                    "ಸ್ಥಳೀಯ ಮಾರಾಟದಿಂದ ಸಾರಿಗೆ ವೆಚ್ಚ ಮತ್ತು ತೂಕ ನಷ್ಟ ಸಂಪೂರ್ಣ ಉಳಿತಾಯವಾಗುತ್ತದೆ.",
                ],
                language="kn",
            )
        elif lang == "hi":
            return AIAdvisory(
                headline=f"{crop_hi} के लिए स्थानीय सत्यापित भाव उपलब्ध — स्थानीय मंडी में ही बिक्री करें",
                harvest_action=f"अपनी स्थानीय {local_name} मंडी में सत्यापित सरकारी दर पर माल बेचें।",
                recommended_mandi=f"{local_name} (सत्यापित स्थानीय बिक्री की अनुशंसा)",
                price_justification=f"आपकी स्थानीय {local_name} मंडी में आज का आधिकारिक मॉडल भाव ₹{local_modal:,.0f}/क्विंटल है (शुद्ध ₹{local_net:,.0f})। निकटवर्ती अन्य मंडियों के सत्यापित भाव उपलब्ध नहीं हैं। अतः अनुमानित आंकड़ों के आधार पर परिवहन जोखिम लेने के बजाय स्थानीय मंडी में बेचना ही सर्वोत्तम है।",
                protection_tips=[
                    f"{crop_hi} को स्थानीय {local_name} मंडी में सुबह समय पर पहुंचाएं।",
                    "स्थानीय बिक्री से परिवहन व्यय और मार्ग में होने वाली नासाडी की पूरी बचत होती है।",
                ],
                language="hi",
            )
        elif lang == "mr":
            return AIAdvisory(
                headline=f"{crop_mr} पिकासाठी स्थानिक अधिकृत दर उपलब्ध — स्थानिक बाजारातच विक्री फायदेशीर",
                harvest_action=f"आपल्या स्थानिक {local_name} बाजार समितीत आजच्या अधिकृत दराने विक्री करा.",
                recommended_mandi=f"{local_name} (स्थानिक बाजार समितीत विक्री योग्य)",
                price_justification=f"आपल्या स्थानिक {local_name} बाजार समितीत आजचा अधिकृत सरकारी भाव ₹{local_modal:,.0f}/क्विंटल (निव्वळ ₹{local_net:,.0f}) आहे. शेजारील पर्यायी बाजारांचे सत्यापित भाव उपलब्ध नाहीत. केवळ अंदाजावर आधारित दूरच्या बाजारात माल नेण्यापेक्षा स्थानिक बाजारातच विक्री करणे सुरक्षित आहे.",
                protection_tips=[
                    f"{crop_mr} स्थानिक {local_name} बाजार समितीत सकाळी लवकर पोहोचवा.",
                    "स्थानिक विक्रीमुळे वाहतूक खर्च आणि वाटेतील वजनाची तूट पूर्णपणे वाचते.",
                ],
                language="mr",
            )
        else:
            return AIAdvisory(
                headline=f"Verified Local Quotation Available for {crop_en} — Local Sale Recommended",
                harvest_action=f"Sell at your local APMC ({local_name}) at verified official rates.",
                recommended_mandi=f"{local_name} (Verified Local Sale Recommended)",
                price_justification=f"Your local market ({local_name}) has an authentic live AGMARKNET quotation of ₹{local_modal:,.0f}/qtl (net ₹{local_net:,.0f}/qtl). Neighboring alternative mandis have not reported official quotations today. Transporting produce to distant markets based on unverified estimates is not recommended. Sell locally to save transit costs and spoilage.",
                protection_tips=[
                    f"Deliver harvested {crop_en} early in the morning to {local_name} for prime auction slotting.",
                    "Local sale avoids transport deductions and preserves 100% of product quality.",
                ],
                language="en",
            )

    # 5. Verified comparison available across both local and alternative mandis (e.g. Belagavi Onion)
    top_mandi = mandi_comparison[0]
    best_mandi_name = top_mandi.get("market", "APMC Mandi")
    modal_price = top_mandi.get("modal_price", 2000.0)
    net_price = top_mandi.get("net_price_per_qtl", modal_price)
    net_gain = top_mandi.get("net_gain_vs_local_total", 0.0)
    dist_km = top_mandi.get("distance_km", 0.0)
    transport_qtl = top_mandi.get("transport_cost_per_qtl", 0.0)
    spoilage_qtl = top_mandi.get("spoilage_deduction_per_qtl", 0.0)

    is_local_best = (top_mandi.get("is_local") or net_gain <= 0.0)

    if lang == "kn":
        if is_local_best:
            headline = f"ಸ್ಥಳೀಯ {local_name} ಮಾರುಕಟ್ಟೆಯಲ್ಲಿಯೇ ಮಾರಾಟ ಮಾಡುವುದು ಅತ್ಯಂತ ಲಾಭದಾಯಕ"
            recommended_mandi = f"{local_name} (ಸ್ಥಳೀಯ ಮಾರುಕಟ್ಟೆಯಲ್ಲಿ ಅತ್ಯುತ್ತಮ ನಿವ್ವಳ ಲಾಭ)"
            price_justification = (
                f"ಸ್ಥಳೀಯ {local_name} ಮಂಡಿಯಲ್ಲಿ ನಿವ್ವಳ ₹{local_net:,.0f}/ಕ್ವಿಂಟಾಲ್ ಸಿಗುತ್ತದೆ. "
                f"ಪರ್ಯಾಯ ಮಾರುಕಟ್ಟೆಗಳಿಗೆ ಸಾಗಿಸಲು ತಗಲುವ ಸಾರಿಗೆ ಮತ್ತು ಸಾಗಾಟ ನಷ್ಟದಿಂದಾಗಿ ಸ್ಥಳೀಯ ಮಂಡಿಯೇ ಗರಿಷ್ಠ ಲಾಭ ನೀಡುತ್ತದೆ."
            )
        else:
            headline = f"{best_mandi_name} ಮಾರುಕಟ್ಟೆಗೆ ಸಾಗಾಟ ಸೂಕ್ತ — ₹{net_gain:,.0f} ಹೆಚ್ಚುವರಿ ನಿವ್ವಳ ಲಾಭ"
            recommended_mandi = best_mandi_name
            price_justification = (
                f"{best_mandi_name} ನಲ್ಲಿ ಕ್ವಿಂಟಾಲ್‌ಗೆ ₹{modal_price:,.0f} ದರವಿದ್ದು, ಸಾರಿಗೆ ವೆಚ್ಚ (₹{transport_qtl:,.0f}) "
                f"ಮತ್ತು ಸಾಗಾಟ ನಷ್ಟ (₹{spoilage_qtl:,.0f}) ಕಳೆದ ನಂತರ ₹{net_price:,.0f} ನಿವ್ವಳ ದರ ಸಿಗುತ್ತದೆ. "
                f"{quantity:.0f} ಕ್ವಿಂಟಾಲ್‌ಗೆ ಸ್ಥಳೀಯ ಮಾರುಕಟ್ಟೆಗಿಂತ ಒಟ್ಟು ₹{net_gain:,.0f} ಹೆಚ್ಚುವರಿ ಲಾಭವಾಗುತ್ತದೆ."
            )

        if risk_level == "HIGH_SPOILAGE_ALERT":
            harvest_action = f"ಮಳೆಯ ಎಚ್ಚರಿಕೆ! ಮುಂದಿನ 72 ಗಂಟೆಗಳಲ್ಲಿ {rain_72h:.1f} ಮಿ.ಮೀ ಮಳೆ ಮತ್ತು {rain_prob:.0f}% ಸಂಭವನೀಯತೆ ಇದೆ. ಕೊಯ್ಲು ಮುಂದೂಡಿ ಅಥವಾ ಕೊಯ್ಲು ಮಾಡಿದ {crop_kn} ತಕ್ಷಣ ಟಾರ್ಪಲಿನ್ ಹೊದಿಸಿ."
        elif risk_level == "HARVEST_WITHIN_48H":
            harvest_action = f"ಮುಂದಿನ 48 ಗಂಟೆಗಳಲ್ಲಿ ಕೊಯ್ಲು ಪೂರ್ಣಗೊಳಿಸಿ. ಮಣ್ಣಿನ ತೇವಾಂಶ ಮತ್ತು ಮಳೆ ಹೆಚ್ಚಾಗುವ ಮುನ್ನ {crop_kn} ಒಣಗಿಸಿ ಮಾರುಕಟ್ಟೆಗೆ ಸಿದ್ಧಪಡಿಸಿ."
        else:
            harvest_action = f"ಅನುಕೂಲಕರ ಒಣ ಹವಾಮಾನ ಇದೆ ({rain_72h:.1f} ಮಿ.ಮೀ ಮಳೆ). {crop_kn} ಕೊಯ್ಲು ಮಾಡಿ, ಬಿಸಿಲಿನಲ್ಲಿ ಒಣಗಿಸಿ ಮಾರುಕಟ್ಟೆಗೆ ಸಾಗಿಸಲು ಇದು ಉತ್ತಮ ಸಮಯ."

        tips = [
            f"{crop_kn} ಅನ್ನು ಸಾಗಿಸುವಾಗ ಗಾಳಿಯಾಡುವ ಗೋಣಿಚೀಲಗಳಲ್ಲಿ ಸರಿಯಾಗಿ ಪ್ಯಾಕ್ ಮಾಡಿ.",
            "ಸಾಗಾಟದ ವಾಹನದಲ್ಲಿ ನೀರು ನಿಲ್ಲದಂತೆ ಮತ್ತು ತೇವಾಂಶ ತಾಗದಂತೆ ಟಾರ್ಪಲಿನ್ ಕಟ್ಟಿ.",
            f"ಮುಂಜಾನೆ ತಂಪಾದ ಸಮಯದಲ್ಲಿ {recommended_mandi} ಗೆ ವಾಹನ ಕಳುಹಿಸಿದರೆ ತೂಕ ನಷ್ಟ ತಪ್ಪಿಸಬಹುದು.",
        ]

    elif lang == "hi":
        if is_local_best:
            headline = f"स्थानीय {local_name} में ही बेचना सर्वोत्तम — अतिरिक्त परिवहन खर्च से बचें"
            recommended_mandi = f"{local_name} (स्थानीय मंडी सर्वोत्तम शुद्ध प्राप्ति)"
            price_justification = (
                f"स्थानीय {local_name} मंडी में शुद्ध प्राप्ति ₹{local_net:,.0f}/क्विंटल है। "
                f"अन्य मंडियों में माल ले जाने पर परिवहन खर्च और वजन कटौती के कारण स्थानीय मंडी ही सबसे लाभदायक है।"
            )
        else:
            headline = f"{best_mandi_name} में बेचना सबसे फायदेमंद — ₹{net_gain:,.0f} का अतिरिक्त शुद्ध लाभ"
            recommended_mandi = best_mandi_name
            price_justification = (
                f"{best_mandi_name} में मॉडल मूल्य ₹{modal_price:,.0f}/क्विंटल है। प्रति क्विंटल ₹{transport_qtl:,.0f} परिवहन "
                f"और ₹{spoilage_qtl:,.0f} पारगमन नुकसान काटने के बाद भी ₹{net_price:,.0f} शुद्ध प्राप्त होगा। "
                f"{quantity:.0f} क्विंटल पर कुल ₹{net_gain:,.0f} का अतिरिक्त मुनाफा होगा।"
            )

        if risk_level == "HIGH_SPOILAGE_ALERT":
            harvest_action = f"भारी बारिश और सड़न का खतरा! 72 घंटों में {rain_72h:.1f} मिमी बारिश और {rain_prob:.0f}% संभावना है। {crop_hi} की कटाई रोकें या तिरपाल से तुरंत सुरक्षित करें।"
        elif risk_level == "HARVEST_WITHIN_48H":
            harvest_action = f"अगले 48 घंटों में {crop_hi} की कटाई अवश्य पूरी कर लें। बारिश शुरू होने से पहले फसल सुरक्षित गोदाम में पहुंचाएं।"
        else:
            harvest_action = f"मौसम पूरी तरह अनुकूल और सूखा है ({rain_72h:.1f} मिमी बारिश)। {crop_hi} की कटाई और मंडी परिवहन के लिए यह सुरक्षित समय है।"

        tips = [
            f"{crop_hi} को प्लास्टिक बैग के बजाय हवादार जूट बोरियों में भरें।",
            "गाड़ी में लोड करते समय नीचे और ऊपर तिरपाल बांधकर बारिश से सुरक्षित रखें।",
            f"सुबह के समय {recommended_mandi} मंडी पहुंचने से वजन में नमी की कटौती नहीं होगी।",
        ]

    elif lang == "mr":
        if is_local_best:
            headline = f"स्थानिक {local_name} बाजारातच विक्री करणे योग्य — वाहतूक खर्च वाचवा"
            recommended_mandi = f"{local_name} (स्थानिक बाजार समिती सर्वोत्तम निव्वळ भाव)"
            price_justification = (
                f"स्थानिक {local_name} बाजारात प्रति क्विंटल निव्वळ ₹{local_net:,.0f} मिळतात. "
                f"इतर बाजारातील भाव जास्त दिसले तरी वाहतूक आणि नासाडीमुळे स्थानिक बाजारातच विक्री सर्वाधिक फायदेशीर ठरते."
            )
        else:
            headline = f"{best_mandi_name} बाजार समितीत विक्री फायदेशीर — ₹{net_gain:,.0f} चा जादा निव्वळ नफा"
            recommended_mandi = best_mandi_name
            price_justification = (
                f"{best_mandi_name} मध्ये सरासरी भाव ₹{modal_price:,.0f}/क्विंटल असून वाहतूक खर्च (₹{transport_qtl:,.0f}) "
                f"व नासाडी (₹{spoilage_qtl:,.0f}) वजा जाता प्रति क्विंटल निव्वळ ₹{net_price:,.0f} मिळतील. "
                f"{quantity:.0f} क्विंटलसाठी एकूण ₹{net_gain:,.0f} जादा नफा मिळेल."
            )

        if risk_level == "HIGH_SPOILAGE_ALERT":
            harvest_action = f"पावसाचा तीव्र इशारा! पुढील ७२ तासांत {rain_72h:.1f} मिमी पाऊस व {rain_prob:.0f}% शक्यता. {crop_mr} काढणी पुढे ढकला किंवा शेतात असल्यास तातडीने ताडपत्रीने झाका."
        elif risk_level == "HARVEST_WITHIN_48H":
            harvest_action = f"पुढील ४८ तासांच्या आत {crop_mr} काढणी पूर्ण करा. पाऊस आणि जमिनीतील ओलावा वाढण्यापूर्वी शेतमाल सुरक्षित ठिकाणी साठवा."
        else:
            harvest_action = f"हवामान पूर्णपणे कोरडे व अनुकूल आहे ({rain_72h:.1f} मिमी पाऊस). {crop_mr} काढणी, प्रतवारी व वाहतुकीसाठी ही उत्तम वेळ आहे."

        tips = [
            f"{crop_mr} गोणपाटाच्या पोत्यात भरूनच सुरक्षित वाहतूक करा.",
            "वाहतुकीदरम्यान पाऊस लागल्यास तातडीने ताडपत्रीचे आच्छादन करा.",
            f"{recommended_mandi} बाजार समितीत सकाळी लवकर शेतमाल घेऊन जा जेणेकरून वजनात घट होणार नाही.",
        ]

    else:
        # English Advisory
        if is_local_best:
            headline = f"Sell {crop_en} at Local Mandi ({local_name}) — Best Net Realization"
            recommended_mandi = f"{local_name} (Local Market Offers Best Net Return)"
            price_justification = (
                f"Your local market ({local_name}) offers a net realization of ₹{local_net:,.0f}/qtl. "
                f"While alternative mandis may show nominal price spreads, transport costs (₹2.50/km/qtl) and transit spoilage "
                f"reduce distant returns. Selling locally yields the highest verified financial return."
            )
        else:
            headline = f"Sell {crop_en} at {best_mandi_name} — Verified Arbitrage Gain of ₹{net_gain:,.0f}"
            recommended_mandi = best_mandi_name
            price_justification = (
                f"{best_mandi_name} offers a modal quotation of ₹{modal_price:,.0f}/qtl. After deducting "
                f"₹{transport_qtl:,.0f}/qtl transport cost and ₹{spoilage_qtl:,.0f}/qtl transit spoilage, "
                f"the net realization is ₹{net_price:,.0f}/qtl, delivering a verified net gain of ₹{net_gain:,.0f} "
                f"over your local market for {quantity:.0f} quintals."
            )

        if risk_level == "HIGH_SPOILAGE_ALERT":
            harvest_action = f"Severe Rain & Spoilage Alert! {rain_72h:.1f} mm rain forecast in next 72h ({rain_prob:.0f}% chance). Delay harvest or shelter {crop_en} immediately."
        elif risk_level == "HARVEST_WITHIN_48H":
            harvest_action = f"Harvest window closing. Complete harvest within 48h before rainfall and soil moisture increase."
        else:
            harvest_action = f"Favorable dry window ({rain_72h:.1f} mm rain). Ideal conditions to harvest and transport {crop_en}."

        tips = [
            f"Package harvested {crop_en} in breathable jute gunny bags.",
            "Secure waterproof tarpaulins over cargo bed to shield from transit moisture.",
            f"Schedule transport to arrive at {recommended_mandi} during early morning hours to preserve freshness.",
        ]

    return AIAdvisory(
        headline=headline,
        harvest_action=harvest_action,
        recommended_mandi=recommended_mandi,
        price_justification=price_justification,
        protection_tips=tips,
        language=lang,
    )


async def generate_ai_advisory(
    crop_info: Dict[str, Any],
    weather_info: Dict[str, Any],
    mandi_comparison: List[Dict[str, Any]],
    quantity: float,
    language: str = "en",
    price_comparison_status: str = "verified_comparison_available",
) -> AIAdvisory:
    """Generates structured AI advisory using Gemini 3.5 Flash Lite, with deterministic fallback."""
    lang = (language or "en").lower().strip()
    if lang not in ["en", "kn", "hi", "mr"]:
        lang = "en"

    # If no mandis within 150 km or price comparison is not fully verified, use strict template
    if not mandi_comparison or price_comparison_status != "verified_comparison_available":
        return build_template_advisory(crop_info, weather_info, mandi_comparison, quantity, lang, price_comparison_status)

    # If no valid API key, return verified grounded template immediately
    if not _is_valid_api_key(GEMINI_API_KEY):
        return build_template_advisory(crop_info, weather_info, mandi_comparison, quantity, lang, price_comparison_status)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        system_instruction = (
            "You are KrishiSetu AI, an expert agricultural economist and agronomist advising smallholder farmers in India. "
            "You MUST strictly adhere to the following GROUNDING RULES:\n"
            "1. ONLY use the exact mandi names, modal prices, net realizable prices, transport costs, and net gains provided in the JSON input.\n"
            "2. NEVER invent, modify, or hallucinate financial numbers or weather numbers.\n"
            "3. Recommend the mandi that ranks first in the mandi_comparison list (highest net_price_per_qtl).\n"
            f"4. Write completely and naturally in the requested language: '{lang}'. Use culturally resonant, respectful agricultural terminology "
            "(Kannada for 'kn', Hindi for 'hi', Marathi for 'mr', English for 'en').\n"
            "5. Output must conform to the specified JSON schema."
        )

        prompt_payload = {
            "crop": crop_info,
            "quantity_quintals": quantity,
            "target_language": lang,
            "weather_assessment": weather_info,
            "mandi_arbitrage_ranking": mandi_comparison,
        }

        # Generate structured advisory using gemini-3.5-flash-lite
        response = client.models.generate_content(
            model=GEMINI_PRIMARY_MODEL,
            contents=json.dumps(prompt_payload),
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=AIAdvisory,
                temperature=0.2,
            ),
        )

        if response.text:
            parsed = json.loads(response.text)
            return AIAdvisory(**parsed)

    except Exception as exc:
        logger.warning(f"Gemini API call failed or timed out: {exc}. Using deterministic template fallback.")

    # Resilient fallback
    return build_template_advisory(crop_info, weather_info, mandi_comparison, quantity, lang, price_comparison_status)


async def generate_chat_reply(
    analysis_context: Dict[str, Any],
    question: str,
    language: str = "en",
) -> str:
    """Answers farmer questions grounded in the current analysis context in regional language."""
    lang = (language or "en").lower().strip()
    if lang not in ["en", "kn", "hi", "mr"]:
        lang = "en"

    # If Gemini API key is available, run grounded LLM generation
    if _is_valid_api_key(GEMINI_API_KEY):
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=GEMINI_API_KEY)
            system_instruction = (
                f"You are KrishiSetu Voice Assistant. You answer smallholder farmers in '{lang}' "
                "(English, Kannada, Hindi, or Marathi). "
                "Base your answer strictly on the provided analysis_context JSON (weather, mandi prices, net gains, harvest advice). "
                "Never invent prices or weather statistics. Keep answers concise, clear, and reassuring (2 to 3 sentences maximum)."
            )

            user_content = json.dumps({"analysis_context": analysis_context, "farmer_question": question})

            resp = client.models.generate_content(
                model=GEMINI_PRIMARY_MODEL,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3,
                ),
            )
            if resp.text and resp.text.strip():
                return resp.text.strip()
        except Exception as exc:
            logger.warning(f"Gemini chat failed: {exc}. Falling back to template reply.")

    # Grounded template Q&A reply
    mandis = analysis_context.get("mandi_comparison", [])
    top_mandi = mandis[0] if mandis else {}
    best_market = top_mandi.get("market", "APMC Mandi")
    net_price = top_mandi.get("net_price_per_qtl", 0)
    net_gain = top_mandi.get("net_gain_vs_local_total", 0)
    weather = analysis_context.get("weather", {})
    risk = weather.get("risk_level", "SAFE_WINDOW")
    rain = weather.get("rain_72h_mm", 0.0)

    q_lower = question.lower()

    if lang == "kn":
        if "price" in q_lower or "rate" in q_lower or "ದರ" in q_lower or "ಬೆಲೆ" in q_lower:
            return f"{best_market} ನಲ್ಲಿ ಕ್ವಿಂಟಾಲ್‌ಗೆ ನಿವ್ವಳ ₹{net_price:,.0f} ಸಿಗುತ್ತದೆ. ಸ್ಥಳೀಯ ಮಾರುಕಟ್ಟೆಗಿಂತ ₹{net_gain:,.0f} ಹೆಚ್ಚಿನ ಲಾಭ ಪಡೆಯಬಹುದು."
        elif "rain" in q_lower or "weather" in q_lower or "ಮಳೆ" in q_lower or "ಹವಾಮಾನ" in q_lower:
            return f"ಮುಂದಿನ 72 ಗಂಟೆಗಳಲ್ಲಿ {rain:.1f} ಮಿ.ಮೀ ಮಳೆ ಮುನ್ಸೂಚನೆ ಇದೆ. ಹವಾಮಾನ ಸ್ಥಿತಿ: {risk}. ಬೆಳೆ ಸುರಕ್ಷತೆಗೆ ಮುನ್ನೆಚ್ಚರಿಕೆ ವಹಿಸಿ."
        else:
            return f"{best_market} ಗೆ ಮಾಲನ್ನು ಕಳುಹಿಸುವುದು ಅತ್ಯಂತ ಸೂಕ್ತವಾಗಿದೆ. ಒಟ್ಟು ₹{net_gain:,.0f} ನಿವ್ವಳ ಲಾಭ ದೊರೆಯುತ್ತದೆ."

    elif lang == "hi":
        if "price" in q_lower or "rate" in q_lower or "दाम" in q_lower or "भाव" in q_lower:
            return f"{best_market} में प्रति क्विंटल शुद्ध ₹{net_price:,.0f} प्राप्त होगा। स्थानीय मंडी से कुल ₹{net_gain:,.0f} अधिक लाभ होगा।"
        elif "rain" in q_lower or "weather" in q_lower or "बारिश" in q_lower or "मौसम" in q_lower:
            return f"अगले 72 घंटों में {rain:.1f} मिमी बारिश का अनुमान है। जोखिम स्तर: {risk}। फसल को नमी से बचाएं।"
        else:
            return f"आपके लिए {best_market} मंडी सबसे लाभदायक विकल्प है, जहां कुल ₹{net_gain:,.0f} का अतिरिक्त फायदा होगा।"

    elif lang == "mr":
        if "price" in q_lower or "rate" in q_lower or "भाव" in q_lower or "किंमत" in q_lower:
            return f"{best_market} मध्ये वाहतूक खर्च वजा जाता निव्वळ ₹{net_price:,.0f}/क्विंटल भाव मिळेल. एकूण ₹{net_gain:,.0f} जास्त फायदा होईल."
        elif "rain" in q_lower or "weather" in q_lower or "पाऊस" in q_lower or "हवामान" in q_lower:
            return f"पुढील ७२ तासांत {rain:.1f} मिमी पावसाचा अंदाज आहे. धोका पातळी: {risk}। शेतमाल सुरक्षित ठेवा."
        else:
            return f"आपल्यासाठी {best_market} बाजार समितीत माल विकणे सर्वोत्तम आहे, जिथे ₹{net_gain:,.0f} अतिरिक्त नफा मिळेल."

    else:
        if "price" in q_lower or "rate" in q_lower:
            return f"The net realizable price at {best_market} is ₹{net_price:,.0f}/qtl, giving you ₹{net_gain:,.0f} extra net profit over local mandi."
        elif "rain" in q_lower or "weather" in q_lower:
            return f"Forecast predicts {rain:.1f} mm rain over next 72 hours with risk classification: {risk}. Follow recommended protection steps."
        else:
            return f"The recommended market is {best_market} with an estimated net gain of ₹{net_gain:,.0f} for your produce batch."
