"""
generators/content_gen.py
──────────────────────────
Uses Google Gemini (free tier) to generate:
  ✦ Structured carousel slide content (JSON array)
  ✦ LinkedIn post captions
  ✦ First engagement comments

Free tier limits (Gemini 2.5 Flash):
  ~1,500 requests/day, ~1M tokens/minute — more than enough for daily posting.
  No credit card required. Register at aistudio.google.com
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

from google import genai
from google.genai import types as genai_types

from config import (
    GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL, GROQ_FALLBACK_MODEL,
    AI_TEMPERATURE, AI_MAX_OUTPUT_TOKENS, MAX_REGEN_ATTEMPTS,
)
from generators.prompts import (
    BASE_SYSTEM, get_system_prompt,
    build_carousel_prompt, build_caption_prompt, build_first_comment_prompt,
)

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Gemini client setup
# ══════════════════════════════════════════════════════════════════════════════

def _get_client() -> genai.Client:
    """Returns an authenticated Gemini client. Safe to call multiple times."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set. "
            "Get a free key at: https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=api_key)


# ══════════════════════════════════════════════════════════════════════════════
# Core Gemini call with primary → fallback model
# ══════════════════════════════════════════════════════════════════════════════

def _call_gemini(prompt: str, low_temp: bool = False, ai_persona: str = "company") -> str:
    """
    Calls text LLM with layered fallback:
      1. gemini-2.5-flash   (Google, free tier, 1M context)
      2. gemini-2.5-flash-lite (Google, smaller but still free)
      3. llama-3.3-70b via Groq (open-source, free 1000 RPD — self-heals if Gemini deprecated)

    Returns the raw text response.
    """
    temperature   = 0.2 if low_temp else AI_TEMPERATURE
    system_prompt = get_system_prompt(ai_persona)

    # ── Tier 1 + 2: Gemini ────────────────────────────────────────────────
    client = _get_client()
    for model_name in [GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL]:
        try:
            config = genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=AI_MAX_OUTPUT_TOKENS,
                top_p=0.95,
            )
            log.info("Calling Gemini | model=%s | temp=%.2f", model_name, temperature)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            text = response.text.strip() if response.text else ""
            if text:
                return text
            log.warning("Model %s returned empty response", model_name)
        except Exception as e:
            log.warning("Gemini model %s failed: %s", model_name, e)
            time.sleep(2)

    # ── Tier 3: Groq (llama-3.3-70b) ─────────────────────────────────────
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from groq import Groq
            log.info("Gemini exhausted — trying Groq fallback: %s", GROQ_FALLBACK_MODEL)
            groq_client = Groq(api_key=groq_key)
            completion = groq_client.chat.completions.create(
                model=GROQ_FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt},
                ],
                temperature=temperature,
                max_tokens=AI_MAX_OUTPUT_TOKENS,
            )
            text = completion.choices[0].message.content.strip()
            if text:
                log.info("Groq fallback succeeded")
                return text
        except Exception as e:
            log.warning("Groq fallback also failed: %s", e)

    raise RuntimeError(
        "All LLM providers failed (Gemini 2.5-flash, Gemini 2.5-flash-lite, Groq llama-3.3-70b). "
        "Check API keys and network connectivity."
    )


# ══════════════════════════════════════════════════════════════════════════════
# JSON output parsing — robust extraction from Gemini responses
# ══════════════════════════════════════════════════════════════════════════════

def _extract_json_array(text: str) -> list[dict]:
    """
    Extracts a JSON array from Gemini's response.
    Handles cases where Gemini wraps JSON in markdown code blocks.

    Returns parsed list or raises ValueError.
    """
    # Strip markdown fences if present
    clean = re.sub(r"```(?:json)?\s*", "", text)
    clean = re.sub(r"```\s*$", "", clean).strip()

    # Find the JSON array boundaries — search from start
    start = clean.find("[")
    end   = clean.rfind("]")
    if start == -1 or end == -1:
        # Try object wrapping a list
        obj_start = clean.find("{")
        if obj_start != -1:
            try:
                obj = json.loads(clean[obj_start:])
                for v in obj.values():
                    if isinstance(v, list):
                        return v
            except Exception:
                pass
        raise ValueError(f"No JSON array found in response: {clean[:300]}")

    json_str = clean[start : end + 1]
    parsed = json.loads(json_str)

    if not isinstance(parsed, list):
        raise ValueError("Parsed JSON is not a list")

    return parsed


# ══════════════════════════════════════════════════════════════════════════════
# Carousel slide generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_carousel_slides(
    topic: str,
    category: str,
    data: dict,
    headline: dict | None = None,
    ai_persona: str = "company",
) -> list[dict]:
    """
    Generates structured carousel slide content using Gemini.

    Returns a list of slide dicts:
      [{"slide_num": 1, "type": "HOOK", "title": "...", "body": "...",
        "stat_callout": "₹47,000 Cr", "icon": "☕"}, ...]

    Falls back to a minimal static set if all AI attempts fail.
    """
    prompt = build_carousel_prompt(topic, category, data, headline, ai_persona=ai_persona)

    for attempt in range(MAX_REGEN_ATTEMPTS + 1):
        try:
            raw = _call_gemini(prompt, low_temp=True, ai_persona=ai_persona)
            slides = _extract_json_array(raw)

            # Validate minimum slide count
            if len(slides) < 4:
                log.warning(
                    "Attempt %d: only %d slides returned — regenerating",
                    attempt + 1, len(slides),
                )
                continue

            # Ensure required fields exist on every slide
            validated = []
            for slide in slides:
                if not slide.get("title") or not slide.get("body"):
                    log.warning("Slide %s missing title/body — skipping", slide.get("slide_num"))
                    continue
                # Truncate if over limit (safety net — 1000 chars fits 6 full sentences of ~150 chars each)
                slide["title"] = slide["title"][:80]
                slide["body"]  = slide["body"][:1000]
                validated.append(slide)

            if len(validated) >= 4:
                log.info("Generated %d carousel slides for topic: %s", len(validated), topic)
                return validated

        except (ValueError, json.JSONDecodeError) as e:
            log.warning("Attempt %d JSON parse error: %s", attempt + 1, e)
        except Exception as e:
            log.warning("Attempt %d Gemini error: %s", attempt + 1, e)
            time.sleep(3)

    # Hard fallback — minimal static slides so the run doesn't fail
    log.error("All Gemini attempts failed — using static fallback slides for: %s", topic)
    return _fallback_slides(topic, category)


def _fallback_slides(topic: str, category: str) -> list[dict]:
    """Full 9-slide fallback carousel — used only when all Gemini attempts fail."""
    is_personal = category.startswith("personal")
    if is_personal:
        return [
            {
                "slide_num": 1, "type": "HOOK",
                "title": "My First Export: What Nobody Tells You",
                "body": "In September 2021 I sent my first 2 MT Robusta shipment to a buyer in Dubai, UAE. The buyer rejected 600 kg because moisture content was 13.1% — the limit is 12.5%. That single rejection cost me \u20b91.8 lakh and nearly ended my export journey in month one. The next morning I drove to a shop in Bengaluru and bought a \u20b91,800 digital grain moisture meter. That \u20b91,800 tool has since protected over 200 MT of cargo worth more than \u20b94 crore. But the moisture problem was only the first of five things I got completely wrong that year.",
                "stat_callout": "\u20b91.8L lost",
                "forward_pull": "Slide 2 reveals the mistake that cost me even more than the moisture problem.",
                "image_prompt": "Close-up of coffee beans being poured into burlap sack on farm, Karnataka plantation, warm golden light, documentary photography, no text",
                "icon": "\u2615"
            },
            {
                "slide_num": 2, "type": "CONTEXT",
                "title": "Why I Almost Quit After Month Three",
                "body": "By November 2021 I had spent \u20b912 lakh on sourcing, packaging, and freight — and received zero confirmed repeat orders. The Coorg estate I was sourcing from had no APEDA registration, which blocked two Italian buyers from placing orders. I didn't know that APEDA registration was a legal export prerequisite until a German broker told me in an email. Getting APEDA took me 6 weeks, \u20b94,200 in fees, and one physical inspection of my warehouse in Krishnarajapete. Without it, no serious EU buyer would touch my invoices regardless of coffee quality. The paperwork nobody talks about almost ended the business before it started.",
                "forward_pull": "Here is the moment the first real international buyer finally said yes — it came from an unexpected direction.",
                "image_prompt": "Indian entrepreneur reviewing export documents at desk, Karnataka office setting, warm light, authentic candid photography, no text",
                "icon": "\ud83d\udcdd"
            },
            {
                "slide_num": 3, "type": "STORY",
                "title": "How I Found My First Repeat Buyer",
                "body": "In Janua   ry 2022 a Belgian importer named Luc contacted me through the Coffee Board of India's buyer directory — a free resource I had ignored for months. He needed 3 MT of Robusta, Grade 1, moisture below 12%, shipped FOB Mangaluru with PHYTOSANITARY certificate. I fulfilled the order in 19 days and he paid within the agreed 30-day credit window — unusual for a first transaction. By April 2022 Luc placed a second order for 8 MT, then a third for 12 MT in August. That one Belgian buyer generated \u20b968 lakh in revenue in 2022 alone. The Coffee Board directory is still the most underused free resource for Indian exporters.",
                "forward_pull": "But one thing almost destroyed the relationship with Luc in month four — the answer is on the next slide.",
                "image_prompt": "Indian coffee exporter on video call with international buyer, laptop, professional home office, warm Karnataka afternoon light, authentic, no text",
                "icon": "\ud83e\udd1d"
            },
            {
                "slide_num": 4, "type": "LESSON",
                "title": "The Logistics Mistake That Nearly Cost Me Everything",
                "body": "In April 2022 I booked freight with a forwarder who quoted \u20b942,000 per 20-foot container — \u20b98,000 cheaper than the next quote. The savings disappeared when the forwarder missed the vessel cutoff by 2 days, and Luc's roastery in Ghent was left without stock for 11 days causing them to lose a retail client. Luc called me directly and gave me 48 hours to arrange replacement stock via air freight — which cost \u20b91.1 lakh more than the original sea freight. I now work with only two pre-vetted freight forwarders who have a 100% on-time record over 3 years. Saving \u20b98,000 on freight cost me \u20b91.1 lakh plus nearly my best buyer relationship. Never choose a forwarder on price alone.",
                "forward_pull": "The certification that unlocked Italy, Germany, and Belgium simultaneously cost me 18 months — here is exactly how I did it.",
                "image_prompt": "Coffee shipping containers at Mangaluru port, India, freight logistics, aerial documentary photography, warm evening light, no text",
                "icon": "\ud83d\udce6"
            },
            {
                "slide_num": 5, "type": "INSIGHT",
                "title": "18 Months to EU Organic: Was It Worth It?",
                "body": "In March 2022 I started the EU Organic certification process under EC 834/2007 with INDOCERT as my accredited body — the full process took 18 months and cost \u20b93.2 lakh in audits, soil tests, and transition documentation. The first audit failed because two of my supplier estates used urea fertiliser within the 3-year conversion window — I had to find replacement certified estates in Coorg and Chikmagalur. Certification was granted in September 2023 for 40 MT annual certified volume across 3 estates. The first EU Organic order from a Munich roastery came at \u20b9485 per kg FOB — 34% above our standard Arabica price that month. In the first 6 months post-certification, EU Organic orders generated \u20b91.4 crore in additional revenue. The 18 months of pain and \u20b93.2 lakh investment paid back within 4 months of certification.",
                "stat_callout": "+34% FOB premium",
                "forward_pull": "The emerging market that surprised me most in 2024 was not in Europe at all — next slide reveals which one.",
                "image_prompt": "EU Organic certification document being reviewed, coffee quality inspector, professional setting, Karnataka India, warm studio lighting, no text",
                "icon": "\u2705"
            },
            {
                "slide_num": 6, "type": "GROWTH",
                "title": "The Market I Almost Missed Completely",
                "body": "In 2023 I ignored UAE enquiries for 6 months because I assumed the Middle East only wanted cheap Robusta blends at commodity prices. A Japanese trading firm representing a UAE specialty roaster contacted me in October 2023 requesting single-origin Coorg Arabica, SCA cupping score above 82, with Full Natural processing — at \u20b9510 per kg CIF Dubai. That single order was 4 MT worth \u20b920.4 lakh — our highest per-kg revenue order to that point. The UAE specialty coffee market grew 28% year-on-year in 2023-24 according to the Dubai Multi Commodities Centre report. I now have 3 active UAE buyers and the market contributes 22% of total revenue. The market I dismissed as low-value turned out to be our most profitable segment by margin.",
                "forward_pull": "What I learned about quality grading changed how I source from Karnataka estates — the next slide explains the exact system I use now.",
                "image_prompt": "Specialty coffee cupping session, professional cupping room, Karnataka India, coffee cups lined up, quality evaluation, warm light, no text",
                "icon": "\ud83c\udf1f"
            },
            {
                "slide_num": 7, "type": "TIP",
                "title": "The Quality System That Eliminated Rejections",
                "body": "After the Dubai moisture rejection in 2021, I built a 5-point quality gate that every batch must pass before leaving our warehouse in Krishnarajapete. Point 1: moisture meter reading below 12.0% on 3 random samples per lot. Point 2: screen size grading — minimum Grade 1 for EU, Grade 2 acceptable for UAE blends. Point 3: visual defect count — maximum 5 primary defects per 300g GREEN sample following Coffee Board India standards. Point 4: cupping score minimum 78 for commercial lots, 82 for specialty lots — conducted every Tuesday morning. Point 5: PHYTOSANITARY certificate arranged minimum 5 days before vessel cutoff. Since implementing this system in January 2022, we have had zero quality rejections across 47 shipments totalling 312 MT.",
                "forward_pull": "Here is where we are today in numbers — and where we are heading by December 2026.",
                "image_prompt": "Coffee quality grading inspection, defect sorting by hand, Karnataka warehouse, detail photography, warm natural light, no text",
                "icon": "\ud83d\udd2c"
            },
            {
                "slide_num": 8, "type": "PROOF",
                "title": "From 2 MT to 200 MT: The Numbers Now",
                "body": "In 2021 I shipped 2 MT total — one order, one buyer, one country. In 2025 VB Exports shipped 200 MT across 14 buyers in 8 countries including Italy, Germany, Belgium, UAE, Japan, Malaysia, UK, and the Netherlands. Revenue grew from \u20b946 lakh in 2022 to \u20b94.1 crore in 2025 — an 8.9x increase over 4 years. We now hold EU Organic, APEDA, FSSAI, and Coffee Board registrations with Rainforest Alliance certification in progress for 2026. Average FOB price across the portfolio is \u20b9398 per kg, up from \u20b9218 per kg in 2021. The next milestone is 500 MT annual volume by December 2027 — and we are exactly on track.",
                "stat_callout": "200 MT · 8 countries",
                "forward_pull": "If you are building your own export journey, the final slide is for you specifically.",
                "image_prompt": "Indian coffee exporter standing confidently at Karnataka plantation, professional portrait in farm setting, golden hour light, authentic, no text",
                "icon": "\ud83d\udcca"
            },
            {
                "slide_num": 9, "type": "CTA",
                "title": "Let's Talk Coffee Exports",
                "body": "I share the real numbers, real mistakes, and real wins from building VB Exports from \u20b946 lakh to \u20b94.1 crore in 4 years. If you are an international buyer looking for Karnataka Robusta or Arabica, I would love to send you a sample and price list. If you are an Indian entrepreneur starting your export journey, DM me — I answer every message personally. Follow me for weekly posts on coffee trade, certifications, Karnataka origin stories, and the lessons I wish someone had shared with me in 2021. Connect on LinkedIn, call or WhatsApp on +91 9449522395, or email info@vb-exports.com.",
                "image_prompt": "Confident Indian entrepreneur in coffee plantation, Karnataka India, professional portrait, golden hour, warm authentic light, no text",
                "icon": "\ud83e\udd1d"
            },
        ]
    # ── Company fallback (coffee_market / global_buyers) ─────────────────
    return [
        {
            "slide_num": 1, "type": "HOOK",
            "title": "India's Coffee Exports: A Global Powerhouse?",
            "body": "India exported 430,000 MT of coffee in 2023-24, ranking 6th globally by volume and generating \u20b947,000 Cr in revenue. Karnataka alone produces 71% of India's total coffee output across 248,000 hectares of estates. Robusta accounts for 60% of export volume, valued at over \u20b928,000 Cr — driven by Italian and Belgian roaster demand. Export revenue grew 18% year-on-year between 2022 and 2024, outpacing Brazil's 11% growth in the same period. The Coffee Board of India projects export volume to cross 500,000 MT by 2027 as new markets in Southeast Asia open. But which crop and region drives this growth, and which buyer countries are accelerating fastest?",
            "stat_callout": "430,000 MT",
            "forward_pull": "Which Indian state makes all of this possible? The production data on slide 2 proves it decisively.",
            "image_prompt": "Dramatic aerial view of vast Karnataka coffee plantation rows, morning mist, golden hour light, cinematic photography, no text",
            "icon": "\u2615"
        },
        {
            "slide_num": 2, "type": "CONTEXT",
            "title": "Karnataka: The Heart of Indian Coffee",
            "body": "Karnataka's Western Ghats region cultivates over 248,000 hectares of coffee estates across Coorg, Chikmagalur, Hassan, and Wayanad districts. The state produces both premium Arabica in Coorg's high-altitude estates above 1,000 metres and high-yield Robusta across Chikmagalur's lower slopes. Over 90% of Karnataka's coffee is shade-grown under a natural forest canopy, preserving bean density and reducing water consumption by 40%. More than 250,000 smallholder farmers depend on coffee cultivation, with average estate size of just 2.5 hectares. GI-tagged varieties — Coorg Arabica and Wayanad Robusta — command 12-18% price premiums in EU specialty markets. So who is actually buying all of this Indian coffee, and in what volumes?",
            "forward_pull": "The buyer concentration data on slide 3 surprises most exporters who assume demand is evenly distributed.",
            "image_prompt": "Lush green Karnataka Western Ghats coffee plantation, shade-grown rows, misty hills at dawn, documentary photography, no text",
            "icon": "\ud83c\udf31"
        },
        {
            "slide_num": 3, "type": "STAT",
            "title": "India's Coffee Export Volume and Value",
            "body": "India exported 430,000 MT of coffee in 2023-24, generating \u20b947,000 Cr in total export revenue — a record high for the country. This represents an 18% increase over the 2021-22 figure of 364,000 MT, driven by Robusta demand from European roasters. Robusta exports alone were valued at over \u20b928,000 Cr, while premium Arabica contributed \u20b919,000 Cr at higher per-kg FOB prices. FOB prices for specialty Arabica ranged \u20b9420-\u20b9480 per kg in Q1 2026, up from \u20b9310-\u20b9350 in Q1 2023. Despite this scale, 70% of Indian coffee is still exported as green bean with minimal value addition — the processing premium remains uncaptured. The price story on the next slide explains exactly which buyer countries pay the highest per-kg premiums.",
            "stat_callout": "\u20b947,000 Cr",
            "forward_pull": "The buyer country breakdown reveals a concentration that most exporters find surprising and commercially important.",
            "image_prompt": "Coffee trade data, global commodity market, business analytics, professional office, warm lighting, no text",
            "icon": "\ud83d\udcca"
        },
        {
            "slide_num": 4, "type": "STAT",
            "title": "Top Importing Countries of Indian Coffee",
            "body": "Italy consistently absorbs 23% of India's total coffee exports — worth over \u20b910,800 Cr annually — making it the single most critical buyer market for Indian Robusta. Germany follows at 12%, purchasing primarily specialty blends from Karnataka estates for its \u20ac8.2B retail coffee market. Russia imports around 8% of Indian coffee, maintaining steady Robusta demand and diversifying away from Brazilian supply since 2022. Belgium, USA, and UAE together account for a further 18% of export volume across different quality tiers. Southeast Asian markets — particularly Indonesia, Malaysia, and Vietnam — grew Indian coffee imports by 40% between 2022 and 2024. Most exporters focus on Italy and Germany, missing the faster-growing Middle East and ASEAN opportunity entirely.",
            "forward_pull": "The hidden supply reliability advantage India has over Brazil and Vietnam is the subject of slide 5.",
            "image_prompt": "World map with trade flow lines from India to Europe, Middle East trade connections, global business, professional, no text",
            "icon": "\ud83c\udf0d"
        },
        {
            "slide_num": 5, "type": "INSIGHT",
            "title": "Karnataka's Supply Reliability Edge",
            "body": "Karnataka maintains consistent annual output averaging 248,000 MT regardless of global weather disruptions that affect Brazilian and Vietnamese production. Over 90% of cultivation is shade-grown, reducing dependence on irrigation and improving bean density — a structural quality advantage that cannot be replicated by sun-grown producers. The state holds 40,000+ hectares of EU Organic and Rainforest Alliance certified or transitioning land, giving buyers access to certified sustainable supply at scale. Contract-backed delivery with 90-day lead time is standard for orders above 5 MT from established Karnataka exporters. Moisture-controlled warehousing at Mangaluru port handles over 80% of all Indian coffee exports with PHYTOSANITARY certification. This combination — consistent volume, certified quality, and documented traceability — is the single advantage Indian coffee has that Brazil cannot easily replicate.",
            "forward_pull": "One certification gap blocks most Indian exporters from accessing the highest-premium EU buyer segment — next slide.",
            "image_prompt": "Karnataka coffee estate, morning harvest, workers picking cherries, shade trees, authentic documentary photography, warm light, no text",
            "icon": "\ud83d\udca1"
        },
        {
            "slide_num": 6, "type": "IMPLICATION",
            "title": "What Buyers Must Verify Before Signing",
            "body": "EU importers must verify APEDA registration and Coffee Board of India export licence before placing any order above 1 MT — both are legally mandatory since 2019. FSSAI licence is required for all food commodity exports from India and must be presented with the commercial invoice. Rainforest Alliance certification adds a verified 8-15% price premium in German and Dutch markets where sustainability compliance is contractually required by major retailers. FOB or CIF incoterms must be explicitly agreed in the proforma invoice before shipment booking, as mismatches cause costly demurrage at EU ports. Moisture content above 12.5% triggers automatic rejection at Hamburg and Antwerp ports, the two largest entry points for Indian coffee into Europe. Missing any of these steps costs Indian exporters millions in demurrage, inventory write-offs, and lost buyer relationships annually.",
            "forward_pull": "The EU Organic certification pathway — the highest commercial value credential for Indian exporters — is explained in full on slide 7.",
            "image_prompt": "Business professionals reviewing export compliance documents, trade agreement, professional meeting room, warm light, no text",
            "icon": "\ud83d\udcbc"
        },
        {
            "slide_num": 7, "type": "TIP",
            "title": "EU Organic: Your Gateway to Premium Europe",
            "body": "EU Organic certification under EC 834/2007 requires annual third-party audits by an APEDA-accredited body such as INDOCERT or OneCert — the full process from application to certification takes 18-24 months and costs \u20b92.5-4 lakh per annum in audit and documentation fees. The most common rejection reason — accounting for 35% of failures — is contamination from adjacent conventional farms using prohibited pesticides within the 3-year conversion buffer zone. Certified farms in Coorg receive 30-50% price premiums from European specialty roasters, making EU Organic the single highest-ROI certification for Karnataka exporters. Over 40,000 hectares of Karnataka coffee land currently holds or is in the process of applying for EU Organic certification. Exporters who complete this process access a \u20b915,000 Cr premium segment that remains largely untapped by Indian sellers. The window to differentiate on organic certification is narrowing as more Indian estates apply — early movers have a 3-5 year advantage.",
            "forward_pull": "The fastest-growing buyer markets in 2026 are not where most Indian exporters are currently focused — slide 8 reveals which ones.",
            "image_prompt": "EU Organic certification seal, quality inspection, coffee certification document, professional photography, warm light, no text",
            "icon": "\u2705"
        },
        {
            "slide_num": 8, "type": "OPPORTUNITY",
            "title": "Emerging Markets: The Next Growth Frontier",
            "body": "Southeast Asian markets like Indonesia and Malaysia grew Indian coffee imports by 40% between 2022 and 2024, driven by expanding specialty coffee culture among urban consumers. The UAE became India's 6th largest coffee buyer in 2023, with specialty Arabica demand rising 28% year-on-year as Dubai positions itself as a regional coffee trading hub. Saudi Arabia imported 12,000 MT of Indian coffee in 2023-24, up from 7,500 MT two years earlier, as Vision 2030 drives café culture expansion across the Kingdom. Eastern European nations including Poland and Romania are increasing Robusta purchases by 18% annually as Italian re-export costs rise post-Brexit. Japan's specialty coffee market, worth \u00a51.2 trillion annually, showed 15% year-on-year growth in Indian single-origin sourcing in 2024. Exporters who establish direct relationships in these markets in 2026 will capture first-mover advantages that compound for years.",
            "forward_pull": "You have seen the opportunity. One question remains: who is your next Karnataka coffee partner?",
            "image_prompt": "Coffee export growth, emerging market trade, port logistics India, aerial view, warm documentary photography, no text",
            "icon": "\ud83d\ude80"
        },
        {
            "slide_num": 9, "type": "CTA",
            "title": "Partner With VB Exports for Premium Coffee",
            "body": "VB Exports sources directly from APEDA-registered, EU Organic certified estates across Coorg, Chikmagalur, and Wayanad in Karnataka, India. We supply Robusta and Arabica in bulk — minimum 1 MT per order — with flexible contract terms and 90-day delivery guaranteed from order confirmation. Our coffee ships FOB Mangaluru with complete documentation: PHYTOSANITARY, Certificate of Origin, Coffee Board quality certificate, and EU Organic certificate where applicable. We serve buyers across Italy, Germany, UAE, Japan, Belgium, and 8 other countries with verified traceability from farm to port. Sample requests, price lists, and sourcing consultations are available within 24 hours of inquiry. Reach out today at info@vb-exports.com or +91 9449522395.",
            "image_prompt": "Two business executives shaking hands, international trade partnership, professional office, signed agreement on table, warm light, no text",
            "icon": "\ud83e\udd1d"
        },
    ]


# ══════════════════════════════════════════════════════════════════════════════
# LinkedIn caption generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_caption(
    topic: str,
    category: str,
    slides: list[dict],
    hashtags: list[str],
) -> str:
    """
    Generates the LinkedIn post caption to accompany the carousel PDF.

    Args:
        topic    : Today's topic
        category : Posting category
        slides   : Generated slide dicts (used for context)
        hashtags : List of hashtags to append

    Returns the full post caption string.
    """
    prompt = build_caption_prompt(topic, category, slides)

    try:
        caption = _call_gemini(prompt, low_temp=False)
        # Append hashtags on a fresh line
        hashtag_line = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
        # Replace any hashtags Gemini put at the end with our curated ones
        caption_no_tags = re.sub(r"(#\w+\s*)+$", "", caption.strip()).strip()
        return f"{caption_no_tags}\n\n{hashtag_line}"

    except Exception as e:
        log.warning("Caption generation failed: %s — using minimal fallback", e)
        hashtag_line = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
        return (
            f"India's {topic} — key 2024 data that every buyer needs to know.\n\n"
            f"📄 Swipe through the full breakdown →\n\n"
            f"{hashtag_line}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# First comment generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_first_comment(caption: str, category: str) -> str:
    """
    Generates a short first comment to post on VB Exports' own carousel post.
    Posted ~45 seconds after the main post to boost early engagement signals.

    Returns comment text string.
    """
    prompt = build_first_comment_prompt(caption, category)
    try:
        comment = _call_gemini(prompt, low_temp=False)
        return comment.strip()[:500]    # LinkedIn comment max is ~1250 chars
    except Exception as e:
        log.warning("First comment generation failed: %s", e)
        return "Which markets are you sourcing Indian coffee from? Drop your country below 🌍"
