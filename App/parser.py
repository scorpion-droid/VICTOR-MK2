def equation_splitter(step:str): 
    step= step.replace(" ", "").strip()

    if "=" not in step:
        return None
    
    left, right = step.split("=", 1)
    return left, right