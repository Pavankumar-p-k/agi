package com.example;
import java.util.List;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

public class App extends Activity {

    private EditText inputNumber1, inputNumber2;
    private TextView resultTextView;
    private Button calculateButton;

    @Override
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        inputNumber1 = findViewById(R.id.input_number_1);
        inputNumber2 = findViewById(R.id.input_number_2);
        resultTextView = findViewById(R.id.result_text_view);
        calculateButton = findViewById(R.id.calculate_button);

        calculateButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                int number1 = Integer.parseInt(inputNumber1.getText().toString());
                int number2 = Integer.parseInt(inputNumber2.getText().toString());
                Calculator calculator = new Calculator();
                int result = calculator.add(number1, number2);
                resultTextView.setText(String.valueOf(result));
            }
        });
    }
}