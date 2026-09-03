"""LLM instructions for Phases III & IV, plus their offline mock outputs."""

BREAKDOWN_SYSTEM = (
    "You are a 1st AD breaking down a screenplay for scheduling. Return JSON: "
    "{scenes: [{scene_id, int_ext, location_type, characters_needed, estimated_time_hours, tags}]}. "
    "scene_id is SCN_001, SCN_002... in script order. int_ext is INT or EXT. location_type MUST be "
    "one of the AVAILABLE VENUE TYPES given (pick the closest). characters_needed uses only the "
    "ROLE IDS given. estimated_time_hours is 1-8. tags are lowercase content flags such as night, "
    "crowd, dialogue, alcohol_reference, violence, music. Keep to MAX SCENES by merging minor "
    "scenes. Use only the text."
)

LOCALIZATION_SYSTEM = (
    "You are a localization producer. Given a cut and a target territory, plan subs/dubs "
    "and list content elements that need a censorship check. Respond with JSON: "
    "{territory, subs: bool, dub: bool, elements_to_check: [{type, tags, scene_id}]}."
)
