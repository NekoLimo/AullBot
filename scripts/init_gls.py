with open("./.history/group_list.json","w",encoding="utf-8") as f:
    json.dump([], f, 
    ensure_ascii=False, 
    indent=2)