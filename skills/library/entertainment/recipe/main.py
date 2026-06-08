from skills.utils import success_response, error_response

RECIPES = [
    {"name": "Vegetable Stir Fry", "cuisine": "chinese", "ingredients": ["broccoli", "carrots", "bell pepper", "soy sauce", "ginger", "garlic", "oil"], "diet": "vegan", "steps": ["Heat oil in wok", "Add garlic and ginger", "Stir fry vegetables", "Add soy sauce", "Cook 5 minutes"], "prep_time": "15 mins"},
    {"name": "Chicken Tikka Masala", "cuisine": "indian", "ingredients": ["chicken", "yogurt", "tomato sauce", "cream", "spices", "garlic", "ginger"], "diet": "any", "steps": ["Marinate chicken in yogurt and spices", "Grill chicken pieces", "Cook tomato sauce with cream", "Add chicken to sauce", "Simmer 20 minutes"], "prep_time": "45 mins"},
    {"name": "Margherita Pizza", "cuisine": "italian", "ingredients": ["pizza dough", "tomato sauce", "mozzarella", "basil", "olive oil"], "diet": "vegetarian", "steps": ["Preheat oven to 220°C", "Roll out dough", "Spread tomato sauce", "Add mozzarella", "Bake 15 minutes", "Top with basil"], "prep_time": "30 mins"},
    {"name": "Greek Salad", "cuisine": "greek", "ingredients": ["tomatoes", "cucumber", "olives", "feta cheese", "onion", "olive oil", "oregano"], "diet": "vegetarian", "steps": ["Chop vegetables", "Add olives and feta", "Drizzle olive oil", "Season with oregano"], "prep_time": "10 mins"},
    {"name": "Tacos", "cuisine": "mexican", "ingredients": ["tortillas", "beef", "lettuce", "tomato", "cheese", "salsa", "sour cream"], "diet": "any", "steps": ["Cook beef with spices", "Warm tortillas", "Assemble with toppings", "Add salsa and sour cream"], "prep_time": "25 mins"},
    {"name": "Sushi Rolls", "cuisine": "japanese", "ingredients": ["sushi rice", "nori", "salmon", "avocado", "cucumber", "soy sauce", "wasabi"], "diet": "any", "steps": ["Cook sushi rice", "Place nori on mat", "Spread rice", "Add fillings", "Roll tightly", "Slice into pieces"], "prep_time": "50 mins"},
    {"name": "Pad Thai", "cuisine": "thai", "ingredients": ["rice noodles", "shrimp", "tofu", "peanuts", "bean sprouts", "lime", "tamarind sauce"], "diet": "any", "steps": ["Soak noodles", "Stir fry shrimp and tofu", "Add noodles and sauce", "Toss with peanuts", "Garnish with sprouts and lime"], "prep_time": "30 mins"},
    {"name": "Beef Burger", "cuisine": "american", "ingredients": ["beef patty", "bun", "lettuce", "tomato", "cheese", "onion", "ketchup"], "diet": "any", "steps": ["Grill patty", "Toast bun", "Assemble with toppings", "Serve with fries"], "prep_time": "20 mins"},
    {"name": "Falafel Wrap", "cuisine": "middle eastern", "ingredients": ["chickpeas", "pita bread", "tahini", "lettuce", "tomato", "cucumber", "cumin"], "diet": "vegan", "steps": ["Blend chickpeas with spices", "Form into balls", "Deep fry until golden", "Stuff in pita", "Add veggies and tahini"], "prep_time": "35 mins"},
    {"name": "Minestrone Soup", "cuisine": "italian", "ingredients": ["beans", "pasta", "carrots", "celery", "tomato", "garlic", "herbs"], "diet": "vegan", "steps": ["Sauté vegetables", "Add tomatoes and broth", "Add beans and pasta", "Simmer 30 minutes"], "prep_time": "40 mins"},
    {"name": "Butter Chicken", "cuisine": "indian", "ingredients": ["chicken", "butter", "cream", "tomato puree", "garam masala", "fenugreek", "ginger garlic paste"], "diet": "any", "steps": ["Marinate chicken", "Cook in butter", "Add tomato puree and spices", "Simmer with cream", "Garnish with fenugreek"], "prep_time": "40 mins"},
    {"name": "Caesar Salad", "cuisine": "american", "ingredients": ["romaine lettuce", "croutons", "parmesan", "caesar dressing", "lemon", "garlic"], "diet": "vegetarian", "steps": ["Chop lettuce", "Make dressing", "Toss together", "Top with croutons and parmesan"], "prep_time": "15 mins"},
    {"name": "Miso Soup", "cuisine": "japanese", "ingredients": ["miso paste", "tofu", "seaweed", "green onion", "dashi stock"], "diet": "vegan", "steps": ["Bring dashi to boil", "Add tofu and seaweed", "Dissolve miso paste", "Garnish with green onion"], "prep_time": "10 mins"},
    {"name": "Spaghetti Carbonara", "cuisine": "italian", "ingredients": ["spaghetti", "eggs", "parmesan", "pancetta", "black pepper", "garlic"], "diet": "any", "steps": ["Cook spaghetti", "Fry pancetta", "Mix eggs with parmesan", "Combine hot pasta with egg mix", "Add pancetta and pepper"], "prep_time": "25 mins"},
    {"name": "Bibimbap", "cuisine": "korean", "ingredients": ["rice", "beef", "spinach", "carrots", "egg", "gochujang", "sesame oil"], "diet": "any", "steps": ["Cook rice", "Sauté beef and vegetables", "Fry egg", "Arrange on rice", "Serve with gochujang"], "prep_time": "35 mins"},
    {"name": "Croissant", "cuisine": "french", "ingredients": ["flour", "butter", "yeast", "sugar", "milk", "salt", "egg"], "diet": "vegetarian", "steps": ["Make dough", "Layer with butter", "Fold repeatedly", "Shape into crescents", "Bake until golden"], "prep_time": "3 hours"},
    {"name": "Guacamole", "cuisine": "mexican", "ingredients": ["avocado", "lime", "tomato", "onion", "cilantro", "jalapeño", "salt"], "diet": "vegan", "steps": ["Mash avocados", "Mix with lime juice", "Add diced tomato and onion", "Season with salt and cilantro"], "prep_time": "10 mins"},
    {"name": "Fish and Chips", "cuisine": "british", "ingredients": ["cod", "potatoes", "flour", "beer", "vinegar", "salt", "oil"], "diet": "any", "steps": ["Cut potatoes into chips", "Batter fish with beer batter", "Deep fry chips", "Deep fry fish", "Serve with vinegar"], "prep_time": "30 mins"},
    {"name": "Hummus", "cuisine": "middle eastern", "ingredients": ["chickpeas", "tahini", "lemon", "garlic", "olive oil", "paprika"], "diet": "vegan", "steps": ["Blend chickpeas with tahini", "Add lemon and garlic", "Drizzle olive oil", "Sprinkle paprika"], "prep_time": "10 mins"},
    {"name": "Tom Yum Soup", "cuisine": "thai", "ingredients": ["shrimp", "lemongrass", "galangal", "chili", "mushrooms", "lime juice", "fish sauce"], "diet": "any", "steps": ["Boil broth with lemongrass", "Add galangal and chili", "Add mushrooms and shrimp", "Season with lime and fish sauce"], "prep_time": "25 mins"},
    {"name": "Ratatouille", "cuisine": "french", "ingredients": ["eggplant", "zucchini", "tomato", "bell pepper", "onion", "garlic", "herbs de provence"], "diet": "vegan", "steps": ["Slice vegetables", "Layer in dish", "Add herbs and garlic", "Bake 40 minutes"], "prep_time": "55 mins"},
    {"name": "Dosa", "cuisine": "indian", "ingredients": ["rice", "urad dal", "fenugreek", "salt", "oil", "potato filling"], "diet": "vegan", "steps": ["Soak rice and dal", "Grind to batter", "Ferment overnight", "Spread on hot griddle", "Add filling and fold"], "prep_time": "12 hours (incl fermentation)"},
    {"name": "Pancakes", "cuisine": "american", "ingredients": ["flour", "eggs", "milk", "butter", "sugar", "baking powder", "maple syrup"], "diet": "vegetarian", "steps": ["Mix dry ingredients", "Add eggs and milk", "Cook on griddle", "Flip when bubbly", "Serve with syrup"], "prep_time": "20 mins"},
    {"name": "Pho", "cuisine": "vietnamese", "ingredients": ["rice noodles", "beef", "beef broth", "star anise", "cinnamon", "bean sprouts", "basil"], "diet": "any", "steps": ["Simmer broth with spices", "Cook noodles", "Slice beef thin", "Assemble bowls", "Pour hot broth over"], "prep_time": "2 hours"},
    {"name": "Chocolate Lava Cake", "cuisine": "french", "ingredients": ["dark chocolate", "butter", "eggs", "flour", "sugar", "vanilla"], "diet": "vegetarian", "steps": ["Melt chocolate and butter", "Mix eggs and sugar", "Fold together with flour", "Bake 12 minutes at 200°C", "Serve immediately"], "prep_time": "25 mins"},
    {"name": "Paneer Butter Masala", "cuisine": "indian", "ingredients": ["paneer", "butter", "cream", "tomato puree", "cashews", "garam masala", "kasuri methi"], "diet": "vegetarian", "steps": ["Fry paneer cubes", "Make cashew tomato gravy", "Add cream and spices", "Simmer with paneer", "Garnish with methi"], "prep_time": "35 mins"},
    {"name": "Pasta Alfredo", "cuisine": "italian", "ingredients": ["fettuccine", "butter", "cream", "parmesan", "garlic", "black pepper"], "diet": "vegetarian", "steps": ["Cook pasta", "Melt butter with garlic", "Add cream and parmesan", "Toss with pasta", "Season with pepper"], "prep_time": "20 mins"},
    {"name": "Spring Rolls", "cuisine": "chinese", "ingredients": ["spring roll wrappers", "cabbage", "carrots", "mushrooms", "soy sauce", "oil"], "diet": "vegan", "steps": ["Shred vegetables", "Stir fry with soy sauce", "Wrap in wrappers", "Deep fry until crispy"], "prep_time": "30 mins"},
    {"name": "Biryani", "cuisine": "indian", "ingredients": ["rice", "chicken", "yogurt", "onions", "saffron", "spices", "ghee"], "diet": "any", "steps": ["Marinate chicken", "Partially cook rice", "Layer chicken and rice", "Add saffron", "Dum cook 30 minutes"], "prep_time": "1 hour"},
    {"name": "Bruschetta", "cuisine": "italian", "ingredients": ["bread", "tomatoes", "basil", "garlic", "olive oil", "balsamic vinegar"], "diet": "vegan", "steps": ["Toast bread slices", "Rub with garlic", "Top with diced tomatoes and basil", "Drizzle olive oil and vinegar"], "prep_time": "10 mins"},
    {"name": "Tiramisu", "cuisine": "italian", "ingredients": ["mascarpone", "ladyfingers", "coffee", "cocoa powder", "eggs", "sugar"], "diet": "vegetarian", "steps": ["Make coffee", "Whip mascarpone with eggs", "Layer ladyfingers and cream", "Dust with cocoa", "Chill 4 hours"], "prep_time": "4.5 hours"},
    {"name": "Shakshuka", "cuisine": "middle eastern", "ingredients": ["eggs", "tomatoes", "bell pepper", "onion", "garlic", "cumin", "paprika"], "diet": "vegetarian", "steps": ["Sauté onion and pepper", "Add tomatoes and spices", "Make wells for eggs", "Poach eggs in sauce", "Serve with bread"], "prep_time": "25 mins"},
]

async def recipe(params: dict) -> dict:
    pool = RECIPES
    cuisine = params.get("cuisine", "").lower()
    ingredient = params.get("ingredient", "").lower()
    diet = params.get("diet", "").lower()
    if cuisine:
        pool = [r for r in pool if r["cuisine"] == cuisine]
    if ingredient:
        pool = [r for r in pool if any(ingredient in ing.lower() for ing in r["ingredients"])]
    if diet in ("vegetarian", "vegan"):
        pool = [r for r in pool if r["diet"] in (diet, "any")]
    if not pool:
        return error_response("No recipes found matching your criteria")
    return success_response({"recipes": pool, "total": len(pool)})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
