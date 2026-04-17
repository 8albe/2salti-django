import json

def test():
    empty = json.dumps({"blocking": [], "warnings": [], "info": []})
    with_error = json.dumps({"blocking": ["error 1"], "warnings": [], "info": []})
    print("Empty:", empty)
    print("With error:", with_error)

test()
