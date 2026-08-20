"""LLM instructions for Phases III & IV, plus their offline mock outputs."""

BREAKDOWN_SYSTEM = (
    "You are a 1st AD breaking down a screenplay. For each scene return JSON: "
    "{scene_id, int_ext, location_type, characters_needed, estimated_time_hours, tags}."
)

LOCALIZATION_SYSTEM = (
    "You are a localization producer. Given a cut and a target territory, plan subs/dubs "
    "and list content elements that need a censorship check. Respond with JSON: "
    "{territory, subs: bool, dub: bool, elements_to_check: [{type, tags, scene_id}]}."
)
