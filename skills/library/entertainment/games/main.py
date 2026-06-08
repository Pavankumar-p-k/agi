import random
from skills.utils import success_response, error_response

WORDS = ["python", "elephant", "rainbow", "astronaut", "guitar", "pizza", "dragon", "galaxy", "butterfly", "mountain"]

async def _ttt_game(params: dict) -> dict:
    board = params.get("board", [" "]*9)
    if len(board) != 9:
        return error_response("Board must have 9 cells")
    pos = params.get("move")
    if pos is not None:
        pos = int(pos)
        if pos < 0 or pos > 8 or board[pos] != " ":
            return error_response("Invalid move")
        board[pos] = "X"
    win_combos = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,b,c in win_combos:
        if board[a] == board[b] == board[c] != " ":
            return success_response({"board": board, "winner": board[a], "game_over": True})
    if " " not in board:
        return success_response({"board": board, "winner": "draw", "game_over": True})
    empty = [i for i, v in enumerate(board) if v == " "]
    ai = random.choice(empty)
    board[ai] = "O"
    for a,b,c in win_combos:
        if board[a] == board[b] == board[c] != " ":
            return success_response({"board": board, "winner": board[a], "game_over": True})
    if " " not in board:
        return success_response({"board": board, "winner": "draw", "game_over": True})
    return success_response({"board": board, "winner": None, "game_over": False})

async def _hangman_game(params: dict) -> dict:
    word = params.get("word")
    if not word:
        word = random.choice(WORDS)
    guessed = params.get("guessed", [])
    guesses_left = params.get("guesses_left", 6)
    letter = params.get("move", "")
    if letter and len(letter) == 1:
        letter = letter.lower()
        if letter in guessed:
            return error_response("Already guessed that letter")
        guessed.append(letter)
        if letter not in word:
            guesses_left -= 1
    display = "".join(c if c in guessed else "_" for c in word)
    if "_" not in display:
        return success_response({"word": word, "display": display, "guessed": guessed, "guesses_left": guesses_left, "status": "won"})
    if guesses_left <= 0:
        return success_response({"word": word, "display": display, "guessed": guessed, "guesses_left": 0, "status": "lost"})
    return success_response({"word": word, "display": display, "guessed": guessed, "guesses_left": guesses_left, "status": "playing"})

async def _guess_game(params: dict) -> dict:
    target = params.get("target")
    if target is None:
        target = random.randint(1, 100)
    guess = params.get("move")
    if guess is None:
        return success_response({"target": target, "message": "Guess a number between 1 and 100"})
    guess = int(guess)
    if guess < target:
        return success_response({"target": target, "hint": "Too low", "correct": False})
    elif guess > target:
        return success_response({"target": target, "hint": "Too high", "correct": False})
    else:
        return success_response({"target": target, "hint": "Correct!", "correct": True})

async def _rps_game(params: dict) -> dict:
    choices = ["rock", "paper", "scissors"]
    move = params.get("move", "").lower()
    if move not in choices:
        return error_response("Choose rock, paper, or scissors")
    ai = random.choice(choices)
    if move == ai:
        result = "draw"
    elif (move == "rock" and ai == "scissors") or (move == "scissors" and ai == "paper") or (move == "paper" and ai == "rock"):
        result = "win"
    else:
        result = "lose"
    return success_response({"player": move, "ai": ai, "result": result})

GAMES = {"tic-tac-toe": _ttt_game, "hangman": _hangman_game, "guess-number": _guess_game, "rps": _rps_game}

async def games(params: dict) -> dict:
    game = params.get("game", "").lower()
    handler = GAMES.get(game)
    if not handler:
        return error_response(f"Unknown game '{game}'. Choose from: {', '.join(GAMES.keys())}")
    return await handler(params)

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
