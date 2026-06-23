package com.example.calculator;

public class CalculatorPresenter {
  private CalculatorView view;

  public CalculatorPresenter(CalculatorView view) {
    this.view = view;
  }

  public void onAddButtonClick(int num1, int num2) {
    int result = num1 + num2;
    view.displayResult(result);
  }
}
