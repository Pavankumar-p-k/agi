
        package com.example.calculator;

        import android.os.Bundle;
        import android.view.View;
        import android.widget.Button;
        import android.widget.EditText;
        import android.widget.TextView;
        import androidx.appcompat.app.AppCompatActivity;

        public class MainActivity extends AppCompatActivity {
            private EditText num1EditText, num2EditText;
            private TextView resultTextView;
            private Button addButton, subtractButton, multiplyButton, divideButton;

            @Override
            protected void onCreate(Bundle savedInstanceState) {
                super.onCreate(savedInstanceState);
                setContentView(R.layout.activity_main);

                num1EditText = findViewById(R.id.num1_edit_text);
                num2EditText = findViewById(R.id.num2_edit_text);
                resultTextView = findViewById(R.id.result_text_view);
                addButton = findViewById(R.id.add_button);
                subtractButton = findViewById(R.id.subtract_button);
                multiplyButton = findViewById(R.id.multiply_button);
                divideButton = findViewById(R.id.divide_button);

                addButton.setOnClickListener(new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        calculateResult("+");
                    }
                });

                subtractButton.setOnClickListener(new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        calculateResult("-");
                    }
                });

                multiplyButton.setOnClickListener(new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        calculateResult("*");
                    }
                });

                divideButton.setOnClickListener(new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        calculateResult("/");
                    }
                });
            }

            private void calculateResult(String operator) {
                double num1 = Double.parseDouble(num1EditText.getText().toString());
                double num2 = Double.parseDouble(num2EditText.getText().toString());

                double result = switch (operator) {
                    case "+" -> num1 + num2;
                    case "-" -> num1 - num2;
                    case "*" -> num1 * num2;
                    case "/" -> num2 != 0 ? num1 / num2 : 0;
                    default -> 0;
                };

                resultTextView.setText(String.valueOf(result));
            }
        }
      