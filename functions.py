from urllib.parse import ParseResult, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from requests.exceptions import RequestException


def parse_url_book_id_page_num(url: str):
    parsed_url = urlparse(url)  # type: ParseResult
    parsed_query = parse_qs(parsed_url.query)  # type: dict

    return (int(parsed_query['mb'][0]), int(parsed_query['part'][0]))


def generate_url(user_url: str, page_num: int):
    parsed_url = urlparse(user_url)  # type: ParseResult
    current_page_url = "{}://{}{}?".format(
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path
    )

    parsed_query = parse_qs(parsed_url.query)  # type: dict

    if 'loveread' in user_url:
        parsed_query['p'] = [page_num]
    else:
        parsed_query['part'] = [page_num]

    for key in parsed_query:
        current_page_url += "{}={}&".format(
            key,
            str(parsed_query[key][0])
        )

    return current_page_url[:-1]


def parse_loveread_book_info(html: str):
    book_title = None
    book_id = None
    last_page_num = None

    soup = BeautifulSoup(html.replace("<br>", "<br />"), "html.parser")
    h2_tag = soup.find('h2')

    if h2_tag:
        # Поиск ссылки внутри тега <h2>
        link = h2_tag.find('a', href=lambda href: href and 'view_global.php' in href)

        if link:
            book_title = link.get_text()
            book_id = link['href'].split('id=')[-1]

    navigation_div = soup.find('div', class_='navigation')

    if navigation_div:
        page_links = navigation_div.find_all('a', href=lambda href: href and 'read_book.php' in href)
        page_numbers = []

        for link in page_links:
            href = link['href']
            # Извлечение номера страницы из ссылки
            page_number = href.split('p=')[-1]
            page_numbers.append(int(page_number))

        last_page_num = max(page_numbers)

    table_of_contents = {
        'Книга': {
            'start_page': 1,
            'end_page': last_page_num
        }
    }

    return book_title, book_id, last_page_num, table_of_contents


def parse_kbk_book_info(html: str):
    soup = BeautifulSoup(html.replace("<br>", "<br />"), "html.parser")
    content = soup.find("div", id="toc")

    div = content.find("div", {"class": "ngg-navigation"})
    navigation_a_tags = div.find_all("a", href=True)

    last_page_num = 0

    for a in navigation_a_tags:
        book_id, current_page_num = parse_url_book_id_page_num(a['href'])

        if current_page_num > last_page_num:
            last_page_num = current_page_num

    title_h1 = content.find("h1", {"class": "series"})

    if not title_h1:
        title_h1 = soup.find("h1", {"class": "title"})

    table_of_contents_ol = content.find("ol")
    table_of_contents_li = table_of_contents_ol.find_all("li", recursive=False)
    table_of_contents = {}
    table_of_contents_last_element_title = None

    for li in table_of_contents_li:
        a = li.find("a", recursive=False)
        book_id, page_num = parse_url_book_id_page_num(a['href'])

        if table_of_contents_last_element_title is not None:
            table_of_contents[table_of_contents_last_element_title]["end_page"] = page_num - 1

        table_of_contents[a.text] = {"start_page": page_num, "end_page": None}
        table_of_contents_last_element_title = a.text

    return title_h1.text, book_id, last_page_num, table_of_contents


def download_page_or_quit(url):
    try:
        response = requests.get(url)
    except RequestException as e:
        print("Could not download the web page: " + str(e))
        quit()

    if response.status_code != 200:
        print("Something went wrong, got status code " +
              str(response.status_code))
        quit()

    return response.text


def parse_page_loveread(html: str):
    soup = BeautifulSoup(html.replace("<br>", "<br />"), "html.parser")
    p_tags = soup.find_all('p', class_='MsoNormal')

    return ''.join(str(p) for p in p_tags)


def parse_page_kbk(html: str):
    soup = BeautifulSoup(html.replace("<br>", "<br />"), "html.parser")
    content = soup.find("div", id="toc")
    content.find("div", {"class": "ngg-navigation"}).decompose()

    for br in content.find_all("br"):
        br.decompose()

    # remove all <ol> <li> <a> tags
    for ol in content.find_all("ol"):
        li = ol.find("li", recursive=False)

        if li is not None:
            a = li.find("a", recursive=False)

            if a is not None:
                ol.decompose()

    for tag in content.find_all("h1"):
        if tag.get_text() == 'СОДЕРЖАНИЕ' or tag.get_text() == 'ПРЕДИСЛОВИЕ':
            tag.decompose()
        elif tag.has_attr("class") and tag.get("class")[0] == "series":
            tag.decompose()
        else:
            b = soup.new_tag("b")
            value = str(tag.get_text())
            b.string = value

            if len(value) > 0:
                b.insert(0, soup.new_tag("br"))

                if len(value) <= 30 and value != "ПЛАН":
                    b.insert(0, soup.new_tag("br"))

            tag.replace_with(b)

    for tag in content.find_all("h2"):
        b = soup.new_tag("b")
        b.string = tag.get_text()

        p = soup.new_tag("p", align="center")
        p.append(b)

        tag.replace_with(p)

    return "\n".join([str(tag) for tag in content.find_all(recursive=False)])


def generate_e_book(
        id: int,
        author: str,
        title: str,
        language: str,
        chapters_dict: dict,
        output_file_without_ext: str,
        table_of_contents_needed=True
):
    book = epub.EpubBook()

    # set metadata
    book.set_identifier(str(id))
    book.set_title(str(title))
    book.set_language(str(language))
    book.add_author(str(author))

    if table_of_contents_needed:
        book.spine = ["nav"]
        i = 0

        for chapter_title in list(chapters_dict.keys()):
            i += 1

            # create chapter
            chapter = epub.EpubHtml(
                title=chapter_title,
                file_name=str(i) + ".xhtml",
                lang=language,
                content=chapters_dict[chapter_title],
            )

            # add chapter
            book.add_item(chapter)
            book.spine.append(chapter)
            book.toc.append(epub.Link(
                href=str(i) + ".xhtml",
                title=chapter_title,
                uid=str(i)
            ))
    else:
        full_content_as_chapter = epub.EpubHtml(
            title=title,
            file_name="book.xhtml",
            lang=language,
            content="\n".join(chapters_dict.values()),
        )
        book.spine = [full_content_as_chapter]
        book.add_item(full_content_as_chapter)

    # add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # write to the file
    epub.write_epub(output_file_without_ext + ".epub", book, {})
