"""Curated "red flag" symptom categories, reviewed with a healthcare
professional as part of the product's clinical-triage design work.

The overall model follows a 4-level clinical priority scale (see
docs/red-flag-padroes-cumulativos-proposta.md for the sourcing --
CDC stroke signs, AHA/ACC chest-pain guidance, WHO/NICE persistent-symptom
and possible-cancer red flags):

- VERMELHO (possible emergency, never duration-gated): RED_FLAG_ABSOLUTE_CATEGORIES
  (a symptom that is, by itself, a sign of a potentially serious condition
  regardless of patient history or how many times it's occurred --
  cardiorrespiratory, neurological, altered consciousness,
  bleeding/trauma/poisoning) and RED_FLAG_CONTEXTUAL_CATEGORIES once their
  matching anamnese risk factor actually applies (see ANAMNESE_RISK_FACTORS /
  CONTEXTUAL_RISK_RULES below) -- e.g. mild shortness of breath is routine
  on its own, but warrants the same urgency as an absolute red flag in a
  patient with heart failure or a recent surgery. Both evaluated from a
  SINGLE check-in's free text by RedFlagDetectionService.
- LARANJA (short-term evaluation, not an emergency): ORANGE_COMBINATION_RULES
  below -- specific, evidence-sourced combinations of otherwise-unremarkable
  signs building up across SEPARATE check-ins (e.g. persistent abdominal
  pain + weight loss). Deliberately NOT a generic "N symptoms in a window"
  count -- the clinical reference this was built from explicitly warns
  against that shape of rule (two mild signs aren't automatically riskier
  than one severe one) -- each rule instead encodes a named, specific
  association. Evaluated by app/bot/scheduler.py's
  _fire_symptom_combination_alert from the patient's already-normalized
  SymptomTerm history, not from a single message.
- AMARELO (scheduled evaluation): the same single symptom recurring across
  a week without a LARANJA-worthy combination -- see
  _fire_symptom_pattern_alert/NotificationKindEnum.SYMPTOM_PATTERN_ALERT in
  app/bot/scheduler.py. No dedicated data structure here since it's a
  single-term repeat count, not a category list.
- VERDE (low immediate risk): the default -- no match against any of the
  above. Reclassification happens automatically on the next check-in that
  changes the picture; no separate mechanism is needed for it.

This module only ever defines what a detector may match against -- it
never invents a category outside these lists. All of it is a clinical
decision, not an engineering one: changing any of it needs the same kind
of review it got the first time, not just a code change.
"""

from dataclasses import dataclass
from typing import Literal

RedFlagTier = Literal["absoluto", "contextual"]
# The 4-level clinical priority scale described above -- distinct from
# RedFlagTier (which is about *how* a match is evaluated: from one
# message vs. from history) since both "absoluto" and "contextual" map to
# the same "vermelho" priority once triggered.
RedFlagPriority = Literal["vermelho", "laranja", "amarelo", "verde"]
PRIORITY_LABELS_PT_BR: dict[RedFlagPriority, str] = {
    "vermelho": "Possível emergência médica",
    "laranja": "Avaliação médica em curto prazo",
    "amarelo": "Avaliação médica programada",
    "verde": "Baixo risco imediato",
}
PRIORITY_BY_RED_FLAG_TIER: dict[RedFlagTier, RedFlagPriority] = {
    "absoluto": "vermelho",
    "contextual": "vermelho",
}


@dataclass(frozen=True)
class RedFlagCategory:
    key: str
    label: str
    tier: RedFlagTier
    # Lay-language examples used to steer the classifier prompt -- not an
    # exhaustive keyword list, the model is expected to generalize beyond
    # these exact phrases.
    example_phrases: tuple[str, ...]


RED_FLAG_ABSOLUTE_CATEGORIES: tuple[RedFlagCategory, ...] = (
    RedFlagCategory(
        key="cardiorrespiratorio",
        label="Sinais cardiorrespiratórios",
        tier="absoluto",
        example_phrases=(
            "não consigo respirar direito",
            "estou ficando sem ar",
            "não consigo puxar o ar",
            "estou sufocando",
            "aperto forte no peito",
            "peso no peito",
            "dor no peito que não passa",
            "dor no peito com suor frio",
            "desmaiei e não sei por quê",
            "coração disparado e quase desmaiando",
            "muito pálido e suando frio de repente",
        ),
    ),
    RedFlagCategory(
        key="neurologico",
        label="Sinais neurológicos súbitos",
        tier="absoluto",
        example_phrases=(
            "minha boca entortou",
            "um lado do rosto caiu",
            "meu braço não responde",
            "não consigo levantar um braço",
            "minha perna não obedece",
            "estou falando enrolado",
            "não consigo encontrar as palavras",
            "não estou entendendo o que falam comigo",
            "perdi a visão de repente",
            "estou vendo dobrado",
            "perdi o equilíbrio do nada",
            "dor de cabeça muito forte que começou de repente",
            "fiquei confuso de repente",
            "tive uma convulsão",
        ),
    ),
    RedFlagCategory(
        key="consciencia",
        label="Alteração de consciência",
        tier="absoluto",
        example_phrases=(
            "a pessoa não responde quando chamo",
            "não consigo ficar em pé, estou quase apagando",
            "respirando estranho e não responde",
        ),
    ),
    RedFlagCategory(
        key="sangramento_trauma_intoxicacao",
        label="Sangramento, trauma ou intoxicação",
        tier="absoluto",
        example_phrases=(
            "sangramento que não para",
            "vomitei sangue",
            "sangue nas fezes",
            "tomei a dose errada do remédio e estou passando mal",
            "engoli algo que pode ser veneno",
            "bati a cabeça forte e fiquei confuso",
            "queimadura grande",
            "levei um choque elétrico forte",
        ),
    ),
)

# Not alarming on their own -- only escalated when the patient's anamnese
# has a matching risk factor (see CONTEXTUAL_RISK_RULES).
RED_FLAG_CONTEXTUAL_CATEGORIES: tuple[RedFlagCategory, ...] = (
    RedFlagCategory(
        key="falta_de_ar_leve",
        label="Falta de ar leve ou moderada",
        tier="contextual",
        example_phrases=(
            "uma falta de ar leve",
            "fiquei um pouco sem ar",
            "cansei mais do que o normal",
            "um chiado no peito",
            "um pouco de dificuldade pra respirar",
        ),
    ),
    RedFlagCategory(
        key="dor_abdominal",
        label="Dor abdominal",
        tier="contextual",
        example_phrases=(
            "dor na barriga",
            "dor abdominal",
            "cólica forte",
            "dor na região do estômago",
        ),
    ),
    RedFlagCategory(
        key="febre",
        label="Febre",
        tier="contextual",
        example_phrases=(
            "estou com febre",
            "febre alta",
            "febre e calafrio",
        ),
    ),
    RedFlagCategory(
        key="inchaco_ou_dor_em_uma_perna",
        label="Inchaço ou dor em uma perna",
        tier="contextual",
        example_phrases=(
            "minha perna inchou",
            "dor e inchaço numa perna só",
            "uma perna ficou quente e vermelha",
        ),
    ),
    RedFlagCategory(
        key="palpitacao",
        label="Palpitação",
        tier="contextual",
        example_phrases=(
            "meu coração está acelerado",
            "senti o coração bater forte",
            "palpitação",
        ),
    ),
    RedFlagCategory(
        key="mal_estar_confusao_leve",
        label="Mal-estar, fraqueza, suor ou tremor súbitos",
        tier="contextual",
        example_phrases=(
            "fiquei fraco e suando do nada",
            "tremendo e confuso",
            "mal-estar súbito",
        ),
    ),
    RedFlagCategory(
        key="sinais_de_descompensacao_cardiaca",
        label="Piora ao deitar, inchaço ou ganho rápido de peso",
        tier="contextual",
        example_phrases=(
            "piora quando eu deito",
            "as pernas incharam",
            "ganhei peso rápido essa semana",
        ),
    ),
    RedFlagCategory(
        key="sangramento_leve",
        label="Sangramento leve",
        tier="contextual",
        example_phrases=(
            "um sangramento pequeno",
            "sangrou um pouco",
            "hematoma que apareceu sozinho",
        ),
    ),
    RedFlagCategory(
        key="dor_de_cabeca_com_alteracao_visual",
        label="Dor de cabeça com alteração visual",
        tier="contextual",
        example_phrases=(
            "dor de cabeça e visão embaçada",
            "dor de cabeça com vista escura",
        ),
    ),
)

RED_FLAG_ALL_CATEGORIES: tuple[RedFlagCategory, ...] = RED_FLAG_ABSOLUTE_CATEGORIES + RED_FLAG_CONTEXTUAL_CATEGORIES
RED_FLAG_CATEGORY_BY_KEY: dict[str, RedFlagCategory] = {category.key: category for category in RED_FLAG_ALL_CATEGORIES}


@dataclass(frozen=True)
class ClinicalSign:
    """A normalized clinical sign referenced by one or more
    OrangeCombinationRules below. `aliases` are the SymptomTerm.label
    values (see SymptomNormalizationService, models.py's SymptomTerm) that
    count as this sign having been reported -- matched case-insensitively,
    never as an exact-string requirement, since the normalizer grows its
    vocabulary freely and the same sign can land under slightly different
    labels for different patients ("Coceira" vs "Prurido")."""

    key: str
    label: str
    aliases: tuple[str, ...]


# Shared registry -- several rules below reference the same sign (e.g.
# weight loss appears in three different combinations), so each alias list
# is defined once.
_WEIGHT_LOSS = ClinicalSign(
    "emagrecimento", "emagrecimento não intencional", ("emagrecimento", "perda de peso", "emagrecimento não intencional")
)
_ABDOMINAL_PAIN = ClinicalSign(
    "dor_abdominal", "dor abdominal", ("dor abdominal", "dor na barriga", "dor no estômago", "dor abdominal alta")
)
_BOWEL_HABIT_CHANGE = ClinicalSign(
    "alteracao_habito_intestinal",
    "alteração do hábito intestinal",
    ("alteração do hábito intestinal", "diarreia", "constipação", "prisão de ventre", "alteração intestinal"),
)
_BLOOD_IN_STOOL = ClinicalSign(
    "sangue_nas_fezes", "sangue nas fezes", ("sangue nas fezes", "fezes com sangue", "sangramento retal")
)
_JAUNDICE_ITCHING = ClinicalSign("coceira", "coceira", ("coceira", "prurido", "pele com coceira", "comichão"))
_DARK_URINE = ClinicalSign("urina_escura", "urina escura", ("urina escura",))
_PERSISTENT_COUGH = ClinicalSign(
    "tosse_persistente", "tosse persistente", ("tosse", "tosse persistente", "tosse seca", "tosse com catarro")
)
_CHEST_DISCOMFORT = ClinicalSign(
    "desconforto_toracico", "desconforto no peito", ("desconforto no peito", "aperto leve no peito")
)
_DYSPNEA = ClinicalSign(
    "falta_de_ar", "falta de ar", ("falta de ar", "cansaço ao respirar", "dificuldade para respirar")
)
_PERSISTENT_VOMITING = ClinicalSign(
    "vomitos_persistentes", "vômitos persistentes", ("vômito", "vômitos", "náusea e vômito", "vômitos persistentes")
)
_GENERAL_MALAISE = ClinicalSign(
    "alteracao_estado_geral", "alteração do estado geral", ("mal-estar", "fraqueza", "alteração do estado geral", "indisposição")
)
_UNEXPLAINED_BLEEDING = ClinicalSign(
    "sangramento_inexplicado", "sangramento inexplicado", ("sangramento", "sangramento inexplicado", "hematoma sem causa")
)
_NEW_OR_GROWING_MASS = ClinicalSign(
    "massa_ou_caroco", "caroço ou massa nova", ("caroço", "nódulo", "massa", "íngua", "caroço que não desaparece")
)

# Proxy for "persistente" in the source guidance: the bot's free-text
# check-in doesn't capture explicit symptom duration or intensity, so
# "reported on >=N separate check-ins within the rule's window" stands in
# for it. This is an approximation, not a literal duration measurement --
# flagged here so it isn't mistaken for one when the physician reviews the
# rules below.
PERSISTENCE_MIN_OCCURRENCES = 2


@dataclass(frozen=True)
class OrangeSignRequirement:
    sign: ClinicalSign
    min_occurrences: int = 1  # 1 = "reported at all"; PERSISTENCE_MIN_OCCURRENCES = "persistent" (see above)


@dataclass(frozen=True)
class OrangeCombinationRule:
    """One evidence-sourced LARANJA combination (see the module docstring
    and docs/red-flag-padroes-cumulativos-proposta.md for the WHO/NICE
    references) -- deliberately a NAMED, specific association rather than
    a generic "N distinct signs" count. `required` must ALL be satisfied;
    `any_of`, when non-empty, needs at least one satisfied;
    `requires_any_other_persistent_sign` encodes the source guidance's
    generic "+ outro sintoma persistente" (any OTHER sign, not already in
    `required`, reported >= PERSISTENCE_MIN_OCCURRENCES times).

    PROVISIONAL: pending review by the responsible physician (the windows
    below default to 21 days -- only the cough rule has direct textual
    support for that specific duration, "tosse persistente por mais de 3
    semanas"; the rest are a reasonable default, not sourced individually)
    -- that's also why firing these is gated behind
    settings.ORANGE_COMBINATION_ALERTS_ENABLED (default off)."""

    key: str
    label: str
    window_days: int
    required: tuple[OrangeSignRequirement, ...]
    any_of: tuple[OrangeSignRequirement, ...] = ()
    requires_any_other_persistent_sign: bool = False


ORANGE_COMBINATION_RULES: tuple[OrangeCombinationRule, ...] = (
    OrangeCombinationRule(
        key="perda_de_peso_mais_sintoma_persistente",
        label="Perda de peso inexplicada associada a outro sintoma persistente",
        window_days=21,
        required=(OrangeSignRequirement(_WEIGHT_LOSS),),
        requires_any_other_persistent_sign=True,
    ),
    OrangeCombinationRule(
        key="habito_intestinal_mais_sangue",
        label="Alteração persistente do hábito intestinal associada a sangue nas fezes",
        window_days=21,
        required=(
            OrangeSignRequirement(_BOWEL_HABIT_CHANGE, min_occurrences=PERSISTENCE_MIN_OCCURRENCES),
            OrangeSignRequirement(_BLOOD_IN_STOOL),
        ),
    ),
    OrangeCombinationRule(
        key="dor_abdominal_persistente_mais_peso",
        label="Dor abdominal persistente associada a perda de peso",
        window_days=21,
        required=(
            OrangeSignRequirement(_ABDOMINAL_PAIN, min_occurrences=PERSISTENCE_MIN_OCCURRENCES),
            OrangeSignRequirement(_WEIGHT_LOSS),
        ),
    ),
    OrangeCombinationRule(
        key="dor_abdominal_mais_ictericia",
        label="Dor abdominal associada a sinais de icterícia (coceira ou urina escura)",
        window_days=21,
        required=(OrangeSignRequirement(_ABDOMINAL_PAIN),),
        any_of=(OrangeSignRequirement(_JAUNDICE_ITCHING), OrangeSignRequirement(_DARK_URINE)),
    ),
    OrangeCombinationRule(
        key="tosse_persistente_mais_sinais_respiratorios_ou_peso",
        label="Tosse persistente associada a perda de peso, desconforto torácico ou falta de ar",
        window_days=21,
        required=(OrangeSignRequirement(_PERSISTENT_COUGH, min_occurrences=PERSISTENCE_MIN_OCCURRENCES),),
        any_of=(
            OrangeSignRequirement(_WEIGHT_LOSS),
            OrangeSignRequirement(_CHEST_DISCOMFORT),
            OrangeSignRequirement(_DYSPNEA),
        ),
    ),
    OrangeCombinationRule(
        key="vomitos_persistentes_mais_sinais",
        label="Vômitos persistentes associados a perda de peso, dor abdominal ou alteração do estado geral",
        window_days=21,
        required=(OrangeSignRequirement(_PERSISTENT_VOMITING, min_occurrences=PERSISTENCE_MIN_OCCURRENCES),),
        any_of=(
            OrangeSignRequirement(_WEIGHT_LOSS),
            OrangeSignRequirement(_ABDOMINAL_PAIN),
            OrangeSignRequirement(_GENERAL_MALAISE),
        ),
    ),
    OrangeCombinationRule(
        key="sangramento_inexplicado_mais_sintoma_persistente",
        label="Sangramento inexplicado associado a outros sintomas persistentes",
        window_days=21,
        required=(OrangeSignRequirement(_UNEXPLAINED_BLEEDING),),
        requires_any_other_persistent_sign=True,
    ),
    OrangeCombinationRule(
        key="massa_ou_caroco_persistente",
        label="Massa ou caroço novo que persiste",
        window_days=21,
        required=(OrangeSignRequirement(_NEW_OR_GROWING_MASS, min_occurrences=PERSISTENCE_MIN_OCCURRENCES),),
    ),
)
ORANGE_COMBINATION_RULE_BY_KEY: dict[str, OrangeCombinationRule] = {rule.key: rule for rule in ORANGE_COMBINATION_RULES}

# The reviewed risk-factor checklist -- field name on Anamnese -> PT-BR
# label shown in the anamnese form. Single source of truth for the model
# columns (app/models/models.py), the API schema (app/models/schemas.py)
# and the rule table below; keep all three in sync with this tuple.
ANAMNESE_RISK_FACTORS: tuple[tuple[str, str], ...] = (
    ("risk_heart_disease", "Doença cardíaca"),
    ("risk_prior_heart_attack", "Infarto prévio"),
    ("risk_prior_stroke_or_tia", "AVC ou AIT (derrame) prévio"),
    ("risk_asthma_or_copd", "Asma ou DPOC"),
    ("risk_heart_failure", "Insuficiência cardíaca"),
    ("risk_diabetes", "Diabetes"),
    ("risk_anticoagulant_use", "Uso de anticoagulante"),
    ("risk_immunosuppression", "Imunossupressão"),
    ("risk_pregnancy_or_postpartum", "Gravidez ou pós-parto"),
    ("risk_active_cancer", "Câncer ativo"),
    ("risk_prior_thrombosis_or_embolism", "Histórico de trombose ou embolia"),
    ("risk_recent_surgery_or_immobilization", "Cirurgia recente ou imobilização prolongada"),
    ("risk_epilepsy", "Epilepsia"),
)
ANAMNESE_RISK_FACTOR_FIELDS: tuple[str, ...] = tuple(field for field, _label in ANAMNESE_RISK_FACTORS)
ANAMNESE_RISK_FACTOR_LABELS: dict[str, str] = dict(ANAMNESE_RISK_FACTORS)

# Which CONTEXTUAL categories each risk factor elevates to red-flag
# urgency. A risk factor not listed here (risk_prior_stroke_or_tia,
# risk_epilepsy) has no CONTEXTUAL rule because its relevant symptoms
# (any neurological change, a seizure at all) are already caught by the
# ABSOLUTE "neurologico" category regardless of history.
CONTEXTUAL_RISK_RULES: dict[str, tuple[str, ...]] = {
    "risk_heart_disease": ("falta_de_ar_leve", "palpitacao"),
    "risk_prior_heart_attack": ("falta_de_ar_leve",),
    "risk_heart_failure": ("falta_de_ar_leve", "sinais_de_descompensacao_cardiaca"),
    "risk_asthma_or_copd": ("falta_de_ar_leve",),
    "risk_diabetes": ("mal_estar_confusao_leve",),
    "risk_anticoagulant_use": ("sangramento_leve", "dor_de_cabeca_com_alteracao_visual"),
    "risk_immunosuppression": ("febre",),
    "risk_pregnancy_or_postpartum": (
        "dor_abdominal",
        "sangramento_leve",
        "falta_de_ar_leve",
        "dor_de_cabeca_com_alteracao_visual",
    ),
    "risk_active_cancer": ("falta_de_ar_leve",),
    "risk_prior_thrombosis_or_embolism": ("falta_de_ar_leve", "inchaco_ou_dor_em_uma_perna"),
    "risk_recent_surgery_or_immobilization": ("falta_de_ar_leve", "inchaco_ou_dor_em_uma_perna"),
}

# Sent to the patient (WhatsApp reply and in-app notification) whenever a
# description matches an ABSOLUTE category. Deliberately covers both
# "this is happening right now" and "this already happened and passed"
# in the same message, rather than trying to infer tense from free text --
# getting that inference wrong in the direction of "it already passed, so
# it's less urgent" is the one failure mode this can't afford, since some
# of these categories (e.g. neurologico) stay urgent even once resolved.
RED_FLAG_SAFETY_MESSAGE_PT_BR = (
    "O que você descreveu pode ser sinal de uma condição que precisa de avaliação "
    "médica urgente. Se isso está acontecendo agora, está piorando ou foi um sintoma "
    "súbito importante, procure atendimento de emergência imediatamente ou ligue para "
    "o SAMU (192). Mesmo que o sintoma já tenha passado, alguns sinais precisam ser "
    "avaliados com urgência."
)

# Same posture as above, for a CONTEXTUAL match -- generic (doesn't name
# the specific risk factor) so it can be reused as-is in both the WhatsApp
# reply and the in-app notification without needing extra context passed
# through the bot's status-string channel. The professional-facing
# notification (built directly in Python, not through that channel) does
# name the specific risk factor -- see notify_red_flag_symptom_contextual.
RED_FLAG_CONTEXTUAL_SAFETY_MESSAGE_PT_BR = (
    "Considerando seu histórico de saúde, o que você descreveu pode ser sinal de algo "
    "que precisa de avaliação médica urgente. Se isso está acontecendo agora ou está "
    "piorando, procure atendimento de emergência imediatamente ou ligue para o SAMU "
    "(192). Mesmo que já tenha passado, vale uma avaliação rápida dado o seu histórico."
)

# Deliberately calmer than the two messages above -- a LARANJA match is
# "worth a short-term evaluation", not an emergency, so it never mentions
# SAMU/192 or urges immediate care. Same non-diagnostic posture: never
# names a condition, only that the combination of signs is worth a
# doctor's look.
RED_FLAG_ORANGE_SAFETY_MESSAGE_PT_BR = (
    "Ao longo dos últimos check-ins você relatou uma combinação de sinais que pode merecer uma "
    "avaliação médica em curto prazo -- mesmo que nenhum deles pareça grave isoladamente. "
    "Considere agendar uma consulta nos próximos dias para investigar."
)
