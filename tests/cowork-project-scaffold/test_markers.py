"""markers is everything the model is allowed to act on in the templates. Its
ids and digests are what render checks the answers against, so both have to be
stable for a template that has not changed and different for one that has.
"""

import scaffold


class DescribeMarkers:
    """The markers command and the Template parsing it reports on."""

    def it_gives_every_marker_a_unique_id(self, runner):
        code, env = runner.run("markers")
        assert code == scaffold.OK
        ids = [m["id"] for m in env["data"]["markers"]]
        assert len(ids) == len(set(ids))
        assert ids

    def it_names_every_marker_in_the_skeleton_with_its_digest(self, runner):
        _, env = runner.run("markers")
        data = env["data"]
        assert set(data["skeleton"]["markers"]) == set(m["id"] for m in data["markers"])
        for m in data["markers"]:
            assert data["skeleton"]["markers"][m["id"]]["digest"] == m["digest"]
        assert set(data["skeleton"]["values"]) == set(scaffold.SUPPLIED)

    def it_computes_a_digest_from_the_marker_text_it_reports(self, markers):
        for m in markers:
            assert m["digest"] == scaffold.digest(m["text"])

    def it_finds_each_optional_section_with_its_heading(self, markers):
        optional = [m for m in markers if m["kind"] == "optional"]
        assert set(m["heading"] for m in optional) == {
            "Diagrams",
            "Section template",
            "Source-quality flags",
        }

    def it_names_the_optional_section_a_fill_sits_inside(self):
        t = scaffold.Template(
            "x.md",
            "<!-- FILL: outside -->\n\n<!-- OPTIONAL SECTION. s -->\n## S\n\n"
            "<!-- FILL: inside -->\n<!-- END OPTIONAL SECTION -->\n",
        )
        assert [(mk.id, mk.inside) for mk in t.markers] == [
            ("x.md:fill-1", None),
            ("x.md:optional-1", None),
            ("x.md:fill-2", "x.md:optional-1"),
        ]

    def it_tells_inline_and_block_forms_apart(self):
        t = scaffold.Template("x.md", "**Status:** <!-- FILL: s -->\n\n<!-- FILL: b\n  more -->\n")
        assert [mk.block for mk in t.markers] == [False, True]

    def it_does_not_take_a_heading_inside_a_code_fence_for_a_heading(self):
        t = scaffold.Template("x.md", "## Real\n\n```\n## Not\n```\n\n<!-- FILL: x -->\n")
        assert t.markers[0].heading == "Real"

    def it_lists_markers_on_stdout_as_human_output(self, runner):
        code, _ = runner.run("markers", json_output=False)
        assert code == scaffold.OK
        assert "maintain-docs.md:optional-1" in runner.out
        assert runner.err == ""
