"""Screenplay intake: Final Draft files are untrusted XML, so a DTD is refused
outright rather than expanded."""
import base64

import pytest

from services import script_intake

FDX = b"""<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Version="1">
  <Content>
    <Paragraph Type="Scene Heading"><Text>int. cab - night</Text></Paragraph>
    <Paragraph Type="Action"><Text>Mara drives through the rain.</Text></Paragraph>
    <Paragraph Type="Character"><Text>Mara</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>Not tonight.</Text></Paragraph>
  </Content>
</FinalDraft>"""

BOMB = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<FinalDraft><Content><Paragraph Type="Action"><Text>&lol2;</Text></Paragraph></Content></FinalDraft>"""

EXTERNAL = b"""<?xml version="1.0"?>
<!DOCTYPE doc [<!ENTITY secret SYSTEM "file:///etc/passwd">]>
<FinalDraft><Content><Paragraph Type="Action"><Text>&secret;</Text></Paragraph></Content></FinalDraft>"""


def _upload(raw: bytes):
    return script_intake.extract("draft.fdx", content_base64=base64.b64encode(raw).decode())


def test_a_final_draft_file_reads_as_a_screenplay():
    result = _upload(FDX)
    assert result["format"] == "fdx"
    assert result["text"].splitlines()[0] == "INT. CAB - NIGHT"
    assert "Mara drives through the rain." in result["text"]


@pytest.mark.parametrize("raw", [BOMB, EXTERNAL, b'<?xml version="1.0"?><!DOCTYPE FinalDraft><FinalDraft/>'])
def test_a_dtd_is_refused_before_anything_is_expanded(raw):
    with pytest.raises(script_intake.ScriptExtractionError, match="DTD"):
        _upload(raw)


def test_broken_xml_is_a_plain_error():
    with pytest.raises(script_intake.ScriptExtractionError, match="Could not parse"):
        _upload(b"<FinalDraft><Content>")
