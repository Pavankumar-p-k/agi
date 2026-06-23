package com.example.calculator

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import kotlinx.android.synthetic.main.activity_calculator.*

class CalculatorActivity : AppCompatActivity(), CalculatorView {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    setContentView(R.layout.activity_calculator)

    buttonAdd.setOnClickListener {
      val num1 = editTextInput1.text.toString().toInt()
      val num2 = editTextInput2.text.toString().toInt()
      val presenter = CalculatorPresenter(this@CalculatorActivity)
      presenter.onAddButtonClick(num1, num2)
    }
  }

  override fun displayResult(result: Int) {
    textViewResult.text = result.toString()
  }
}
