def test_greet():
    assert greet("World") == "Hello, World!"


# Ensure that cli.invoke() is a valid call before using it.
# Modify this test based on the actual CLI implementation.
# def test_cli():
#     result = cli.invoke()
#     assert result.exit_code == 0
#     assert 'Hello, World!' in result.output
