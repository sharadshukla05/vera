"""
Trigger Router — maps trigger kinds to prompt strategy configs.
Each strategy tells the prompt builder HOW to frame the message.
"""

from typing import TypedDict, Optional


class TriggerStrategy(TypedDict):
    framing: str           # opening framing style
    compulsion_levers: list[str]  # which levers to use
    cta_style: str         # "binary" | "open_ended" | "none"
    voice_note: str        # additional tone instruction
    urgency_multiplier: float  # how much to emphasize urgency


# Canonical strategies per trigger kind
TRIGGER_STRATEGIES: dict[str, TriggerStrategy] = {

    "research_digest": {
        "framing": "knowledge_share",
        "compulsion_levers": ["curiosity", "reciprocity", "specificity"],
        "cta_style": "open_ended",
        "voice_note": "Lead with the specific finding. Mention trial size / source. Ask if they want to see or share it.",
        "urgency_multiplier": 0.8,
    },

    "regulation_change": {
        "framing": "compliance_alert",
        "compulsion_levers": ["loss_aversion", "specificity", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Peer helping peer comply. Not alarmist, just timely. Include the deadline date.",
        "urgency_multiplier": 1.4,
    },

    "perf_dip": {
        "framing": "data_anchored_concern",
        "compulsion_levers": ["loss_aversion", "specificity", "social_proof"],
        "cta_style": "binary",
        "voice_note": "State the exact drop %. Compare to peer median if available. Offer to investigate cause.",
        "urgency_multiplier": 1.3,
    },

    "perf_spike": {
        "framing": "positive_momentum",
        "compulsion_levers": ["curiosity", "social_proof", "reciprocity"],
        "cta_style": "open_ended",
        "voice_note": "Celebrate the spike with specifics. Ask what drove it — make the merchant feel smart.",
        "urgency_multiplier": 0.6,
    },

    "milestone_reached": {
        "framing": "celebration_with_next_step",
        "compulsion_levers": ["social_proof", "curiosity", "effort_externalization"],
        "cta_style": "open_ended",
        "voice_note": "Acknowledge the milestone with the exact number. Immediately pivot to the next milestone or opportunity.",
        "urgency_multiplier": 0.5,
    },

    "dormant_with_vera": {
        "framing": "re_engagement_curiosity",
        "compulsion_levers": ["curiosity", "loss_aversion", "specificity"],
        "cta_style": "open_ended",
        "voice_note": "Don't mention dormancy directly. Lead with something interesting about their category or a number from their own account.",
        "urgency_multiplier": 1.0,
    },

    "renewal_due": {
        "framing": "value_recap_with_stakes",
        "compulsion_levers": ["loss_aversion", "social_proof", "specificity"],
        "cta_style": "binary",
        "voice_note": "Remind what they'd lose (visibility, leads, profile maintenance). Give exact days remaining. Make renewing the obvious choice.",
        "urgency_multiplier": 1.5,
    },

    "winback_eligible": {
        "framing": "value_proof_winback",
        "compulsion_levers": ["loss_aversion", "social_proof", "curiosity"],
        "cta_style": "binary",
        "voice_note": "What has the merchant missed? Quantify the gap since expiry. Make it easy to restart.",
        "urgency_multiplier": 1.1,
    },

    "festival_upcoming": {
        "framing": "seasonal_opportunity",
        "compulsion_levers": ["loss_aversion", "social_proof", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Name the festival. Give days-until. Reference what peer merchants are doing. Offer to set up the campaign.",
        "urgency_multiplier": 0.9,
    },

    "ipl_match_today": {
        "framing": "real_time_event",
        "compulsion_levers": ["loss_aversion", "specificity", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Name the match, teams, time. This is time-sensitive — say so. Offer to post a match-night special.",
        "urgency_multiplier": 2.0,
    },

    "review_theme_emerged": {
        "framing": "operational_insight",
        "compulsion_levers": ["specificity", "loss_aversion", "asking_the_merchant"],
        "cta_style": "open_ended",
        "voice_note": "Quote the theme, give occurrence count. If negative: frame as fixable. If positive: how to amplify?",
        "urgency_multiplier": 1.2,
    },

    "competitor_opened": {
        "framing": "competitive_intelligence",
        "compulsion_levers": ["loss_aversion", "social_proof", "specificity"],
        "cta_style": "binary",
        "voice_note": "Name the competitor and distance. Compare their offer vs merchant's offer. Suggest differentiation angle.",
        "urgency_multiplier": 1.0,
    },

    "cde_opportunity": {
        "framing": "professional_development",
        "compulsion_levers": ["curiosity", "effort_externalization", "specificity"],
        "cta_style": "open_ended",
        "voice_note": "Name the webinar/event, date, speaker if available. Mention credits and cost. Keep it colleague-to-colleague.",
        "urgency_multiplier": 1.2,
    },

    "curious_ask_due": {
        "framing": "genuine_curiosity",
        "compulsion_levers": ["asking_the_merchant", "reciprocity"],
        "cta_style": "open_ended",
        "voice_note": "Ask a single, specific, answerable question about their business this week. Not generic. Make it feel like you're genuinely curious.",
        "urgency_multiplier": 0.4,
    },

    "active_planning_intent": {
        "framing": "action_mode",
        "compulsion_levers": ["effort_externalization", "specificity"],
        "cta_style": "open_ended",
        "voice_note": "CRITICAL: Merchant already said YES or expressed intent. DO NOT re-qualify. Jump straight to concrete next step. Draft something, propose something specific.",
        "urgency_multiplier": 1.8,
    },

    "recall_due": {
        "framing": "care_reminder",
        "compulsion_levers": ["loss_aversion", "specificity", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Customer-facing. Name the service due, months elapsed, offer concrete slots. Warm but professional.",
        "urgency_multiplier": 1.3,
    },

    "chronic_refill_due": {
        "framing": "health_continuity_reminder",
        "compulsion_levers": ["loss_aversion", "specificity", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Customer-facing. List the molecules / medicines. Give the run-out date. Offer home delivery if saved.",
        "urgency_multiplier": 1.6,
    },

    "trial_followup": {
        "framing": "warm_follow_up",
        "compulsion_levers": ["curiosity", "effort_externalization", "specificity"],
        "cta_style": "binary",
        "voice_note": "Customer-facing. Reference the trial date and what they tried. Offer next session slot. Low-pressure.",
        "urgency_multiplier": 1.0,
    },

    "customer_lapsed_soft": {
        "framing": "we_miss_you",
        "compulsion_levers": ["loss_aversion", "social_proof", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Customer-facing. How long since last visit. What's new or improved. One specific offer to come back.",
        "urgency_multiplier": 1.0,
    },

    "customer_lapsed_hard": {
        "framing": "winback_offer",
        "compulsion_levers": ["loss_aversion", "social_proof", "specificity"],
        "cta_style": "binary",
        "voice_note": "Customer-facing. Acknowledge the gap. Reference previous service/focus. Make the return frictionless.",
        "urgency_multiplier": 1.1,
    },

    "supply_alert": {
        "framing": "urgent_compliance_alert",
        "compulsion_levers": ["loss_aversion", "specificity", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Pharmacy only. Name the molecule, batch numbers, manufacturer. Urgency 5 — lead with the action needed.",
        "urgency_multiplier": 2.0,
    },

    "category_seasonal": {
        "framing": "seasonal_demand_intel",
        "compulsion_levers": ["specificity", "loss_aversion", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Pharmacy/category context. Name the trending products and % uplift. Suggest shelf action.",
        "urgency_multiplier": 1.0,
    },

    "gbp_unverified": {
        "framing": "profile_health_alert",
        "compulsion_levers": ["loss_aversion", "specificity", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Unverified GBP = invisible to searches. Quantify the uplift (estimated %). Walk them through verification path.",
        "urgency_multiplier": 1.2,
    },

    "seasonal_perf_dip": {
        "framing": "seasonal_reassurance_with_action",
        "compulsion_levers": ["social_proof", "specificity", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Normalize the seasonal dip with data (peer merchants also see it). But pivot to an action to capture off-season demand.",
        "urgency_multiplier": 0.7,
    },

    "appointment_tomorrow": {
        "framing": "preparation_reminder",
        "compulsion_levers": ["effort_externalization", "specificity"],
        "cta_style": "open_ended",
        "voice_note": "Customer-facing. Tomorrow's appointment. Time, location, what to bring. Optional: ask if anything changed.",
        "urgency_multiplier": 1.5,
    },

    "wedding_package_followup": {
        "framing": "bridal_journey_nudge",
        "compulsion_levers": ["loss_aversion", "specificity", "effort_externalization"],
        "cta_style": "binary",
        "voice_note": "Customer-facing. Reference wedding date and days remaining. Name the next prep step. Create gentle urgency.",
        "urgency_multiplier": 1.2,
    },
}


def get_strategy(trigger_kind: str) -> TriggerStrategy:
    """Return the strategy for a trigger kind, with fallback."""
    return TRIGGER_STRATEGIES.get(trigger_kind, {
        "framing": "general_value_add",
        "compulsion_levers": ["curiosity", "specificity"],
        "cta_style": "open_ended",
        "voice_note": "Be specific, relevant, and concise.",
        "urgency_multiplier": 1.0,
    })
