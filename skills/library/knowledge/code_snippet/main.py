from skills.utils import success_response, error_response

TEMPLATES = {
    "python": {
        "read file": {"code": "with open('file.txt', 'r') as f:\n    content = f.read()\nprint(content)", "explanation": "Opens a file in read mode using a context manager, reads entire content, and prints it."},
        "write file": {"code": "with open('file.txt', 'w') as f:\n    f.write('Hello, World!')", "explanation": "Opens a file in write mode and writes a string to it."},
        "list comprehension": {"code": "squares = [x**2 for x in range(10)]\nprint(squares)", "explanation": "Creates a list of squares from 0 to 9 using list comprehension."},
        "dictionary iteration": {"code": "for key, value in my_dict.items():\n    print(f'{key}: {value}')", "explanation": "Iterates over key-value pairs in a dictionary."},
        "sort list": {"code": "sorted_list = sorted(my_list, reverse=True)", "explanation": "Returns a new sorted list; pass reverse=True for descending order."},
        "filter list": {"code": "evens = [x for x in numbers if x % 2 == 0]", "explanation": "Filters a list to keep only even numbers using list comprehension."},
        "map function": {"code": "doubled = list(map(lambda x: x * 2, numbers))", "explanation": "Applies a lambda function to each element using map."},
        "reduce": {"code": "from functools import reduce\nresult = reduce(lambda a, b: a * b, numbers)", "explanation": "Reduces a list to a single value by applying a function cumulatively."},
        "enumerate": {"code": "for i, item in enumerate(items):\n    print(i, item)", "explanation": "Iterates with both index and value using enumerate."},
        "zip": {"code": "for a, b in zip(list1, list2):\n    print(a, b)", "explanation": "Pairs elements from multiple iterables element-wise."},
        "try except": {"code": "try:\n    result = 10 / x\nexcept ZeroDivisionError:\n    print('Cannot divide by zero')", "explanation": "Catches and handles a specific exception."},
        "json parse": {"code": "import json\ndata = json.loads(json_string)\nprint(data['key'])", "explanation": "Parses a JSON string into a Python dictionary."},
        "http request": {"code": "import httpx\nr = httpx.get('https://api.example.com')\nprint(r.json())", "explanation": "Makes an HTTP GET request and parses JSON response."},
        "class definition": {"code": "class MyClass:\n    def __init__(self, name):\n        self.name = name\n    def greet(self):\n        return f'Hello, {self.name}'", "explanation": "Defines a class with constructor and method."},
        "async function": {"code": "import asyncio\n\nasync def fetch_data():\n    await asyncio.sleep(1)\n    return 'data'\n\nresult = asyncio.run(fetch_data())", "explanation": "Defines and runs an async function."},
        "threading": {"code": "import threading\n\ndef worker():\n    print('Working')\n\nthread = threading.Thread(target=worker)\nthread.start()\nthread.join()", "explanation": "Creates and starts a thread, then waits for it to complete."},
        "regular expression": {"code": "import re\nmatches = re.findall(r'\\d+', 'abc123def456')\nprint(matches)", "explanation": "Finds all digit sequences in a string using regex."},
        "decorator": {"code": "def timer(func):\n    def wrapper(*args, **kwargs):\n        import time\n        start = time.time()\n        result = func(*args, **kwargs)\n        print(f'Time: {time.time() - start}s')\n        return result\n    return wrapper\n\n@timer\ndef slow_func():\n    import time; time.sleep(1)", "explanation": "Defines a decorator that measures execution time."},
        "generator": {"code": "def count_up_to(n):\n    i = 0\n    while i < n:\n        yield i\n        i += 1\n\nfor num in count_up_to(5):\n    print(num)", "explanation": "A generator function that yields values lazily."},
        "pandas read csv": {"code": "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.head())", "explanation": "Reads a CSV file into a pandas DataFrame and shows first rows."},
    },
    "javascript": {
        "fetch api": {"code": "fetch('https://api.example.com')\n  .then(r => r.json())\n  .then(data => console.log(data))", "explanation": "Makes an HTTP request using the Fetch API and logs JSON response."},
        "async await": {"code": "async function fetchData() {\n  const r = await fetch('https://api.example.com');\n  const data = await r.json();\n  console.log(data);\n}", "explanation": "Async function using await for HTTP requests."},
        "array map": {"code": "const doubled = numbers.map(x => x * 2);", "explanation": "Transforms each element of an array using map."},
        "filter": {"code": "const evens = numbers.filter(x => x % 2 === 0);", "explanation": "Filters array elements that satisfy a condition."},
        "reduce": {"code": "const sum = numbers.reduce((acc, x) => acc + x, 0);", "explanation": "Reduces an array to a single accumulated value."},
        "object destructuring": {"code": "const { name, age } = person;\nconsole.log(name, age);", "explanation": "Extracts properties from an object into variables."},
        "spread operator": {"code": "const combined = [...arr1, ...arr2];", "explanation": "Spreads elements of arrays into a new array."},
        "arrow function": {"code": "const add = (a, b) => a + b;", "explanation": "Concise arrow function syntax for a simple operation."},
        "promise all": {"code": "const results = await Promise.all([\n  fetch(url1),\n  fetch(url2)\n]);", "explanation": "Runs multiple promises concurrently and waits for all."},
        "class": {"code": "class Animal {\n  constructor(name) {\n    this.name = name;\n  }\n  speak() {\n    console.log(`${this.name} makes a noise.`);\n  }\n}", "explanation": "ES6 class definition with constructor and method."},
        "dom selector": {"code": "document.querySelector('.my-class').textContent = 'Hello';", "explanation": "Selects a DOM element by CSS selector and sets its text."},
        "event listener": {"code": "button.addEventListener('click', () => {\n  alert('Clicked!');\n});", "explanation": "Adds a click event listener to an element."},
        "local storage": {"code": "localStorage.setItem('key', 'value');\nconst val = localStorage.getItem('key');", "explanation": "Stores and retrieves data from browser local storage."},
        "set timeout": {"code": "setTimeout(() => {\n  console.log('Delayed');\n}, 1000);", "explanation": "Executes a function after a specified delay in milliseconds."},
        "template literal": {"code": "const greeting = `Hello, ${name}!`;", "explanation": "String interpolation using template literals."},
    },
    "typescript": {
        "interface": {"code": "interface User {\n  id: number;\n  name: string;\n  email?: string;\n}", "explanation": "Defines a TypeScript interface with optional property."},
        "type alias": {"code": "type Status = 'active' | 'inactive' | 'pending';", "explanation": "Defines a union type alias."},
        "generic function": {"code": "function identity<T>(arg: T): T {\n  return arg;\n}", "explanation": "A generic function that works with any type."},
        "enum": {"code": "enum Color {\n  Red,\n  Green,\n  Blue\n}\nconst c: Color = Color.Green;", "explanation": "Defines an enum with numeric values."},
        "async typed": {"code": "async function fetchUser(id: number): Promise<User> {\n  const r = await fetch(`/api/users/${id}`);\n  return r.json();\n}", "explanation": "Typed async function that returns a Promise of a User."},
    },
    "rust": {
        "hello world": {"code": "fn main() {\n    println!(\"Hello, World!\");\n}", "explanation": "Standard Rust entry point that prints to stdout."},
        "function": {"code": "fn add(a: i32, b: i32) -> i32 {\n    a + b\n}", "explanation": "A typed function returning the sum of two integers."},
        "vector iteration": {"code": "let numbers = vec![1, 2, 3];\nfor n in &numbers {\n    println!(\"{}\", n);\n}", "explanation": "Creates a vector and iterates over its elements."},
        "struct": {"code": "struct Person {\n    name: String,\n    age: u32,\n}\n\nlet p = Person { name: \"Alice\".to_string(), age: 30 };", "explanation": "Defines a struct and creates an instance."},
        "match": {"code": "match x {\n    1 => println!(\"one\"),\n    2 | 3 => println!(\"two or three\"),\n    _ => println!(\"other\"),\n}", "explanation": "Pattern matching with multiple arms and a catch-all."},
        "option handling": {"code": "fn maybe_value() -> Option<i32> {\n    Some(42)\n}\n\nif let Some(v) = maybe_value() {\n    println!(\"{}\", v);\n}", "explanation": "Handles an Option type with if-let pattern."},
        "error handling": {"code": "use std::fs::File;\n\nfn read_file() -> Result<String, std::io::Error> {\n    let mut f = File::open(\"file.txt\")?;\n    let mut s = String::new();\n    f.read_to_string(&mut s)?;\n    Ok(s)\n}", "explanation": "Function that returns a Result and uses the ? operator."},
    },
    "go": {
        "hello world": {"code": "package main\n\nimport \"fmt\"\n\nfunc main() {\n    fmt.Println(\"Hello, World!\")\n}", "explanation": "Standard Go entry point printing to stdout."},
        "http server": {"code": "package main\n\nimport (\n    \"fmt\"\n    \"net/http\"\n)\n\nfunc handler(w http.ResponseWriter, r *http.Request) {\n    fmt.Fprintf(w, \"Hello!\")\n}\n\nfunc main() {\n    http.HandleFunc(\"/\", handler)\n    http.ListenAndServe(\":8080\", nil)\n}", "explanation": "A minimal HTTP server with a handler function."},
        "goroutine": {"code": "go func() {\n    fmt.Println(\"Running concurrently\")\n}()", "explanation": "Launches an anonymous function as a goroutine."},
        "struct": {"code": "type Person struct {\n    Name string\n    Age  int\n}\n\np := Person{Name: \"Alice\", Age: 30}", "explanation": "Defines a struct and creates an instance."},
        "slice iteration": {"code": "numbers := []int{1, 2, 3}\nfor i, n := range numbers {\n    fmt.Println(i, n)\n}", "explanation": "Iterates over a slice using range, getting index and value."},
        "error handling": {"code": "f, err := os.Open(\"file.txt\")\nif err != nil {\n    log.Fatal(err)\n}\ndefer f.Close()", "explanation": "Opens a file with error checking and deferred close."},
    },
    "bash": {
        "list files": {"code": "for f in *; do\n    echo \"$f\"\ndone", "explanation": "Iterates over all files in the current directory."},
        "find and replace": {"code": "sed -i 's/old/new/g' file.txt", "explanation": "Replaces all occurrences of 'old' with 'new' in a file."},
        "check disk usage": {"code": "df -h | grep '/dev/'", "explanation": "Shows disk usage in human-readable format for device filesystems."},
        "grep search": {"code": "grep -rn \"pattern\" /path/to/search", "explanation": "Recursively searches for a pattern showing line numbers."},
        "backup file": {"code": "cp file.txt{,.bak}", "explanation": "Creates a backup copy of file.txt as file.txt.bak."},
        "count lines": {"code": "wc -l file.txt", "explanation": "Counts the number of lines in a file."},
        "extract tar": {"code": "tar -xzf archive.tar.gz -C /target/dir", "explanation": "Extracts a gzipped tar archive to a target directory."},
    },
    "sql": {
        "select all": {"code": "SELECT * FROM users;", "explanation": "Selects all columns and rows from a table."},
        "select where": {"code": "SELECT name, email FROM users WHERE active = 1;", "explanation": "Selects specific columns with a WHERE condition."},
        "join": {"code": "SELECT u.name, o.total\nFROM users u\nJOIN orders o ON u.id = o.user_id;", "explanation": "Inner join combining users and orders on user ID."},
        "group by": {"code": "SELECT department, COUNT(*) as count\nFROM employees\nGROUP BY department;", "explanation": "Groups rows and counts employees per department."},
        "order by": {"code": "SELECT * FROM products ORDER BY price DESC;", "explanation": "Selects all products ordered by price descending."},
        "insert": {"code": "INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com');", "explanation": "Inserts a new row into the users table."},
        "update": {"code": "UPDATE users SET email = 'new@example.com' WHERE id = 1;", "explanation": "Updates an existing row's email column."},
        "delete": {"code": "DELETE FROM users WHERE id = 1;", "explanation": "Deletes a row matching the condition."},
        "create table": {"code": "CREATE TABLE users (\n    id INT PRIMARY KEY AUTO_INCREMENT,\n    name VARCHAR(100),\n    email VARCHAR(255) UNIQUE\n);", "explanation": "Creates a new table with id, name, and email columns."},
        "subquery": {"code": "SELECT name FROM users\nWHERE id IN (\n    SELECT user_id FROM orders WHERE total > 100\n);", "explanation": "Subquery to find users with orders over 100."},
        "index": {"code": "CREATE INDEX idx_email ON users(email);", "explanation": "Creates an index on the email column for faster lookups."},
        "limit": {"code": "SELECT * FROM users LIMIT 10 OFFSET 20;", "explanation": "Selects 10 rows starting from row 21 (pagination)."},
        "like": {"code": "SELECT * FROM users WHERE name LIKE 'A%';", "explanation": "Finds users whose name starts with 'A'."},
    },
}

async def code_snippet(params: dict) -> dict:
    language = params.get("language", "").strip().lower()
    task = params.get("task", "").strip().lower()
    action = params.get("action", "generate").strip().lower()

    if not language:
        return error_response("Please provide a 'language' parameter.")
    if language not in TEMPLATES:
        supported = ", ".join(sorted(TEMPLATES.keys()))
        return error_response(f"Unsupported language '{language}'. Supported: {supported}")

    if action == "explain":
        results = []
        for tname, tdata in TEMPLATES[language].items():
            results.append({
                "task": tname,
                "code": tdata["code"],
                "explanation": tdata["explanation"]
            })
        return success_response({
            "language": language,
            "snippets": results,
            "count": len(results)
        })

    if not task:
        return error_response("Please provide a 'task' description for the code snippet.")

    matches = []
    task_lower = task.lower()
    for tname, tdata in TEMPLATES[language].items():
        if task_lower in tname.lower() or task_lower in tdata["explanation"].lower():
            matches.append({
                "task": tname,
                "code": tdata["code"],
                "explanation": tdata["explanation"]
            })

    if not matches:
        return error_response(f"No snippet found for '{task}' in {language}.")

    return success_response({
        "language": language,
        "snippets": matches,
        "count": len(matches)
    })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
