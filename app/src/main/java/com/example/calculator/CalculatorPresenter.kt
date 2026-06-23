package com.example.calculator

class CalculatorPresenter(val view: CalculatorView) {
  fun onAddButtonClick(num1: Int, num2: Int) {
    val result = num1 + num2
    view.displayResult(result)
  }
}
