import PyPDF2
import os

input_path = os.path.expanduser("~/Downloads/11 th MATHS volume 1&2 full material tm.pdf")
output_dir = "pdf_output"
os.makedirs(output_dir, exist_ok=True)

with open(input_path, 'rb') as f:
    reader = PyPDF2.PdfReader(f)
    total = len(reader.pages)
    print(f"Total pages: {total}")
    
    # Part 1: pages 1-171 (indices 0-170)
    writer1 = PyPDF2.PdfWriter()
    for i in range(0, 171):
        writer1.add_page(reader.pages[i])
    with open(os.path.join(output_dir, "maths_vol1_2_pages1-171.pdf"), 'wb') as out1:
        writer1.write(out1)
    
    # Part 2: pages 172-end (indices 171 to end)
    writer2 = PyPDF2.PdfWriter()
    for i in range(171, total):
        writer2.add_page(reader.pages[i])
    with open(os.path.join(output_dir, "maths_vol1_2_pages172-end.pdf"), 'wb') as out2:
        writer2.write(out2)
    
    print(f"Created: {output_dir}/maths_vol1_2_pages1-171.pdf")
    print(f"Created: {output_dir}/maths_vol1_2_pages172-end.pdf")
