from core.tools.pdf_tools import do_generate_pdf

result = do_generate_pdf('{"title": "Test Report", "content": "This is a test report content."}')
print('Result:', result)