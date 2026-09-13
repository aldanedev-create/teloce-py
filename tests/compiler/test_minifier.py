from teloce.compiler.minifier import minify_css, minify_js


def test_js_minifier_preserves_literals_and_ambiguous_slashes():
    source = r'''// comment
    const text = "keep  spaces // here";
    const regex = /https?:\/\/example\.com/;
    function value(a) { return a / /two/; }
    '''
    output = minify_js(source)
    assert "keep  spaces // here" in output
    assert r"/https?:\/\/example\.com/" in output
    assert "a / /two/" in output
    assert "// comment" not in output


def test_css_minifier_preserves_quoted_values_and_calc_spacing():
    source = '/* comment */ .card { content: "a  b"; width: calc(100% - 1rem); }'
    output = minify_css(source)
    assert 'content:"a  b"' in output
    assert "calc(100% - 1rem)" in output
    assert "/* comment */" not in output
