from argparse import ArgumentParser
import functions

# todo: сделать парсинг содержания с разбиением по главам,
# чтобы работали ссылки на содержание
parser = ArgumentParser()
parser.add_argument("-u", "--url", default=None)
user_url = parser.parse_args().url

if user_url is None:
    print("Please specify an URL of the book using --url=")
    quit()

response_html = functions.download_page_or_quit(user_url)
book_title, book_id, last_page_num = functions.parse_book_info(response_html)
clean_content = ""

for page_num in range(1, last_page_num + 1):
    page_url = functions.generate_url(user_url, page_num)
    response_html = functions.download_page_or_quit(page_url)
    clean_content += functions.parse_page(response_html)

filename = book_title.replace(" ", "_")

functions.generate_e_book(
    id=book_id,
    title=book_title,
    language="ru",
    author="КБК",
    html_content=clean_content,
    output_file_without_ext=filename
)

print("Done: " + filename)
