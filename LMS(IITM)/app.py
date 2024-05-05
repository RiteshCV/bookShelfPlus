from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify, send_from_directory
import sqlite3
from datetime import datetime, timedelta
import os
import re

app = Flask(__name__)
app.secret_key = 'LnL4N76q.Z2@VT!eE3robW8y.FTc.9cef7Q@37A.8icj2kFu!_bheFX68Y-9.7Bca9AeGj-VUh8ayYV7AtYsAVhi7moE_KWszaRh'
app.config['DATABASE'] = 'identifier.sqlite'


def get_db():
    db = getattr(g, 'my_DB.sqlite', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route('/')
def home():
    db = get_db()
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    user_type = 'User'
    if 'email' in session:
        email = session['email']
        cur.execute("SELECT * FROM Users WHERE Email = ?", (email,))
        user = cur.fetchone()
        user = dict(user)
        user['Usr_Name'] = user['Usr_Name'].replace(' ', '_')
        table_name = f"{user['Usr_Name']}_{user['Usr_ID']}"
        cur.execute(f"SELECT Book_ID, Deadline, Downloaded, Status FROM {table_name}")
        books = cur.fetchall()
        cur.execute(f" SELECT Usr_Type FROM Users WHERE Email = ?", (email,))
        user_type = cur.fetchone()[0]
        curr_books = []
        comp_books = []
        best_sellers = []
        if len(books) > 0:
            getting_started = 0
            comp_count = 0
            for book in books:
                cur.execute("SELECT B_Name, Genre, Auth_Name, Content_Rated, Cover_Page, "
                            "Rating FROM Books WHERE Book_ID = ?", (book["Book_ID"],))
                book_info = cur.fetchone()
                if book["Status"] in ('Reading', 'Requested'):
                    curr_books.append({**book, **book_info})
                elif book["Status"] == 'Returned' and comp_count < 5:
                    comp_count += 1
                    comp_books.append({**book, **book_info})
            cur.row_factory = None
            cur.execute(f"SELECT Book_ID FROM {table_name} ORDER BY COALESCE(Rating, Date_of_Issue), "
                        f"Date_of_Issue LIMIT 5")
            b_id_str = cur.fetchall()
            cur.row_factory = sqlite3.Row
            b_id_str = [x[0] for x in b_id_str]
            cur.execute(f"SELECT DISTINCT Genre FROM Books WHERE Book_ID IN ({','.join('?' * len(b_id_str))})",
                        b_id_str)
            genres = cur.fetchall()
            genre_names = ', '.join([str(x['Genre']) for x in genres])
            cur.execute(f"SELECT Book_ID, B_Name, Auth_Name, Content_Rated, Cover_Page, Rating FROM Books "
                        f"WHERE Genre IN ('{genre_names}') AND Book_ID NOT IN (SELECT Book_ID FROM {table_name} "
                        f"WHERE STATUS IN ('Reading', 'Returned', 'Requested')) "
                        f"ORDER BY CAST(Rating AS INT), Date_of_Release DESC LIMIT 3")
            recommended_books = cur.fetchall()
            b_id_str2 = [x['Book_ID'] for x in recommended_books]
            if len(recommended_books) < 5:
                placeholders = ','.join('?' * len(b_id_str2))
                limit_adjustment = max(0, 7 - len(recommended_books))
                cur.execute(f"SELECT Book_ID, B_Name, Auth_Name, Content_Rated, Cover_Page, Rating FROM Books "
                            f"WHERE Book_ID NOT IN (SELECT Book_ID FROM {table_name} "
                            f"WHERE STATUS IN ('Reading', 'Returned', 'Requested'))"
                            f"AND Book_ID NOT IN ({placeholders}) "
                            f"ORDER BY CAST(Rating AS INT), Date_of_Release DESC "
                            f"LIMIT {limit_adjustment}", b_id_str2)
                recommended_books += cur.fetchall()
            db.commit()
        else:
            getting_started = 1
            cur.execute(f"SELECT Book_ID, B_Name, Auth_Name, Content_Rated, Cover_Page, "
                        f"Rating FROM Books WHERE Genre IN ('Fantasy', 'Classic', 'Thriller') LIMIT 10")
            recommended_books = cur.fetchall()
            db.commit()
        logged_in = True
    else:
        user = {}
        getting_started = 0
        curr_books = []
        comp_books = []
        recommended_books = []
        cur.execute(f'''SELECT Books.* FROM Books INNER JOIN Requests ON Books.Book_ID = Requests.Book_ID 
                    GROUP BY Books.Book_ID ORDER BY COUNT(Requests.Book_ID) DESC LIMIT 5''')
        best_sellers = cur.fetchall()
        logged_in = False
    cur.execute(f'''SELECT * FROM Books ORDER BY Date_of_Release DESC LIMIT 10''')
    new_releases = cur.fetchall()
    db.close()
    return render_template('home.html', logged_in=logged_in, user=user, user_type=user_type,
                           getting_started=getting_started, curr_books=curr_books, comp_books=comp_books,
                           recommended_books=recommended_books, best_sellers=best_sellers, new_releases=new_releases)


@app.route('/books', methods=['GET', 'POST'])
def get_books():
    query = request.args.get('query')
    if not query:
        query = '%'
    db = get_db()
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    logged_in = False
    user_type = 'User'
    if 'email' in session:
        logged_in = True
        cur.execute(f" SELECT Usr_Type FROM Users WHERE Email = ?", (session['email'],))
        user_type = cur.fetchone()[0]
    cur.execute("""
        SELECT DISTINCT Books.*
        FROM Books
        INNER JOIN Sections ON Books.Sec_ID = Sections.Sec_ID
        WHERE Books.B_Name LIKE ? OR
              Books.Auth_Name LIKE ? OR
              Sections.Sec_Name LIKE ?
    """, (f'%{query}%', f'%{query}%', f'%{query}%'))
    books = cur.fetchall()
    cur.execute("""SELECT * FROM Sections WHERE Sec_Name LIKE ?""", (f'%{query}%',))
    sections = cur.fetchall()
    if ' ' not in query:
        filtered_books = [dict(row) for row in books]
        filtered_sections = [dict(row) for row in sections]
        if query == '%':
            query = None
            books = filtered_books
            sections = filtered_sections
        else:
            books = [book for book in filtered_books
                     if any(str(word).lower().startswith(query.lower()) for word in book['B_Name'].split())]
            sections = [section for section in filtered_sections
                        if any(str(word).lower().startswith(query.lower()) for word in section['Sec_Name'].split())]
    db.close()
    return render_template('books.html', user_type=user_type, books=books,
                           sections=sections, query=query, logged_in=logged_in)


@app.route('/sections', methods=['GET', 'POST'])
def get_sections():
    logged_in = False
    user_type = 'User'
    db = get_db()
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    if 'email' in session:
        logged_in = True
        cur.execute(f" SELECT Usr_Type FROM Users WHERE Email = ?", (session['email'],))
        user_type = cur.fetchone()[0]
    cur.execute("SELECT * FROM Sections")
    sections = [dict(row) for row in cur.fetchall()]
    db.close()
    return render_template('sections.html', sections=sections, logged_in=logged_in, user_type=user_type)


@app.route('/section/<int:section_id>', methods=['GET', 'POST'])
def get_section(section_id):
    logged_in = False
    user_type = 'User'
    db = get_db()
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    if 'email' in session:
        logged_in = True
        cur.execute(f" SELECT Usr_Type FROM Users WHERE Email = ?", (session['email'],))
        user_type = cur.fetchone()[0]
    cur.execute("SELECT * FROM Books WHERE Sec_ID = ?", (section_id,))
    books = [dict(row) for row in cur.fetchall()]
    db.close()
    return render_template('books.html', books=books, logged_in=logged_in, user_type=user_type)


@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        dob = request.form['DOB']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        dob_check = datetime.strptime(dob, '%Y-%m-%d').date()
        if not bool(re.match(r'^[\w.-]+@[a-zA-Z0-9.-]+(\.[a-zA-Z]+)$', email)):
            return render_template('createAcc.html', error_message='Invalid Email')
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM Users WHERE Email = ?", (email,))
        existing_email_count = cur.fetchone()[0]
        db.close()
        if existing_email_count > 0:
            return render_template('createAcc.html', error_message='Email already exists')
        if dob_check > datetime.now().date() + timedelta(days=365):
            return render_template('createAcc.html', error_message='Age must be 1+')
        if dob_check > datetime.now().date():
            return render_template('createAcc.html', error_message='Date of Birth must be earlier than today')
        if len(username) < 5:
            return render_template('createAcc.html', error_message='Username must be least 5 characters')
        if len(username) > 20:
            return render_template('createAcc.html', error_message='Username must be within 20 characters')
        if len(password) < 8:
            return render_template('createAcc.html', error_message='Password must be at least 8 characters')
        if password == confirm_password:
            db = get_db()
            cur = db.cursor()
            cur.execute('Insert into Users (passwrd, usr_Name, Date_of_Birth, Email, Acc_Creation) '
                        'values (?, ?, ?, ?, ?)', (password, username, dob, email, datetime.now().date()))
            db.commit()
            cur.execute('update Users set Acc_Status = ? where Email = ?', ('Active', email))
            db.commit()
            usr_id = cur.lastrowid
            username = username.replace(' ', '_')
            table_name = f"{username}_{usr_id}"
            cur.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} ( Req_ID INTEGER NOT NULL ,
                            Book_ID INTEGER NOT NULL, Date_of_Issue DATE,
                            Deadline DATE, Date_of_Return DATE, Status TEXT NOT NULL,
                            Feedback TEXT,Rating REAL DEFAULT 0, Downloaded TEXT DEFAULT 'No', Download_date DATE, 
                            Current_Page INTEGER DEFAULT 1,
                            foreign key (Req_ID) references Requests(Req_ID), 
                            foreign key (Book_ID) references Books(Book_ID))''')
            db.commit()
            cur.close()
            session['email'] = email
            return redirect(url_for('home'))
        else:
            return render_template('createAcc.html', error_message='Passwords do not match')
    else:
        return render_template('createAcc.html')


def perform_login(email, password):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT passwrd FROM Users where Email = ?', (email,))
    actual_password = cur.fetchone()
    if actual_password and actual_password[0] == password:
        if email not in session:
            session['email'] = email
            cur.execute('UPDATE Users SET Acc_Status = ? WHERE Email = ?', ('Active', session['email']))
            db.commit()
            cur.close()
        return True
    else:
        return False


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['Email']
        password = request.form['password']
        if not bool(re.match(r'^[\w.-]+@[a-zA-Z0-9.-]+(\.[a-zA-Z]+)$', email)):
            return render_template('login.html', hide_create_account=False, error_message='Invalid Email or password')
        if perform_login(email, password):
            return redirect(url_for('home'))
        else:
            return render_template('login.html', hide_create_account=False, error_message='Invalid Email or password')
    return render_template('login.html', hide_create_account=False)


@app.route('/login_librarian', methods=['GET', 'POST'])
def login_librarian():
    if request.method == 'POST':
        email = request.form['Email']
        password = request.form['password']
        if not bool(re.match(r'^[\w.-]+@[a-zA-Z0-9.-]+(\.[a-zA-Z]+)$', email)):
            return render_template('login.html', hide_create_account=True, error_message='Invalid Email or password')
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (email,))
        user = cur.fetchone()
        db.commit()
        db.close()
        if not user:
            return render_template('login.html', hide_create_account=True, error_message='Invalid Email or password')
        if user[0] != 'Librarian':
            return render_template('login.html', hide_create_account=True, error_message='Please login as a User')
        if perform_login(email, password):
            return redirect(url_for('home'))
        else:
            return render_template('login.html', hide_create_account=True, error_message='Invalid Email or password')
    return render_template('login.html', hide_create_account=True)


@app.route('/Manage', methods=['GET', 'POST'])
def manage():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (session['email'],))
    user_type = cur.fetchone()[0]
    if user_type == 'Librarian':
        return render_template('Manage.html', user_type=user_type)
    else:
        return render_template('login.html', error_message='Please login as a Librarian')


@app.route('/manage/addBook', methods=['GET', 'POST'])
def add_book():
    if 'email' in session:
        email = session['email']
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (email,))
        user_type = cur.fetchone()[0]
        if user_type != 'Librarian':
            return jsonify({'error': 'Please login as a Librarian'}), 403
        try:
            # Retrieve form data from request
            book_data = {
                'B_Name': request.form['B_Name'],
                'Auth_Name': request.form['Auth_Name'],
                'Genre': request.form['Genre'],
                'No_of_Pages': int(request.form['No_of_Pages']),
                'Content_Rated': request.form['Content_Rated'],
                'Date_of_Release': datetime.strptime(request.form['Date_of_Release'], '%Y-%m-%d').date(),
                'Rating': float(request.form['Rating']),
                'Price': float(request.form['Price']),
                'Cover_Page': request.form.get('Cover_Page', ''),
                'Description': request.form.get('Description', ''),
                'PDF': request.form.get('PDF', '')
            }
            if not all(book_data.values()):
                return jsonify({'error': 'All fields are required'}), 400
            if ((book_data['Rating'] < 0 or book_data['Rating'] > 5 or book_data['No_of_Pages'] < 0
                    or book_data['Price'] < 0 or book_data['Content_Rated'] not in ['E', 'PG', 'PG-13', 'R'])
                    or book_data['Date_of_Release'] > datetime.now().date()):
                return jsonify({'error': 'Invalid Data'}), 400
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT * FROM books WHERE B_Name = ? AND Auth_Name = ? AND No_of_Pages = ?",
                        (book_data['B_Name'], book_data['Auth_Name'], book_data['No_of_Pages']))
            existing_book = cur.fetchone()
            if existing_book:
                return jsonify({'error': 'Book already exists'}), 400
            cur.execute("""
                        INSERT INTO Books (B_Name, Auth_Name, Genre, No_of_Pages, Content_Rated, Date_of_Release,
                                           Availability, Sec_ID, Rating, Price, Cover_Page, Description, PDF)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                book_data['B_Name'],
                book_data['Auth_Name'],
                book_data['Genre'],
                book_data['No_of_Pages'],
                book_data['Content_Rated'],
                book_data['Date_of_Release'],
                'Available',
                0,
                book_data['Rating'],
                book_data['Price'],
                book_data['Cover_Page'],
                book_data['Description'],
                book_data['PDF']
            ))
            db.commit()
            db.close()
            return jsonify({'message': 'Book added successfully'}), 200

        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return redirect(url_for('login'))


@app.route('/api/requests/pending')
def get_pending_requests():
    db = get_db()
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    cur.execute("SELECT * FROM Requests WHERE Status = 'Pending'")
    pending_requests = cur.fetchall()
    pending_requests = [dict(row) for row in pending_requests]
    db.close()
    return jsonify(pending_requests)


@app.route('/api/requests/approve', methods=['POST'])
def approve_request():
    request_data = request.json
    request_id = request_data['request_id']
    comment = request_data['comment']
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE Requests SET Status = 'Approved', Comment = ? WHERE Req_ID = ?", (comment, request_id,))
    db.commit()
    cur.execute("SELECT Usr_ID FROM Requests WHERE Req_ID = ?", (request_id,))
    user_id = cur.fetchone()[0]
    cur.execute("SELECT Usr_Name FROM Users WHERE Usr_ID = ?", (user_id,))
    user_name = cur.fetchone()[0]
    user_name = user_name.replace(' ', '_')
    table_name = f"{user_name}_{user_id}"
    cur.execute(f"UPDATE {table_name} SET Status = 'Approved' WHERE Req_ID = ?", (request_id,))
    db.commit()
    db.close()
    return jsonify({'message': f'Request {request_id} approved with comment: {comment}'})


@app.route('/api/requests/reject', methods=['POST'])
def reject_request():
    request_data = request.json
    request_id = request_data['request_id']
    comment = request_data['comment']
    return jsonify({'message': f'Request {request_id} rejected with comment: {comment}'})


@app.route('/account')
def profile():
    if 'email' in session:
        email = session['email']
        db = get_db()
        cur = db.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute(f" SELECT Usr_Type FROM Users WHERE Email = ?", (session['email'],))
        user_type = cur.fetchone()[0]
        cur.execute("SELECT * FROM Users WHERE Email = ?", (email,))
        user = cur.fetchone()
        user = dict(user)
        user['Usr_Name'] = user['Usr_Name'].replace(' ', '_')
        table_name = f"{user['Usr_Name']}_{user['Usr_ID']}"
        cur.execute(f"SELECT count(*) FROM {table_name} WHERE Status = 'Returned'")
        returned_count = cur.fetchone()[0]
        cur.execute(f"SELECT count(*) FROM {table_name} WHERE Downloaded = 'Yes'")
        downloaded_count = cur.fetchone()[0]
        db.commit()
        db.close()
        return render_template('account.html', user=user,
                               returned_count=returned_count, downloaded_count=downloaded_count, user_type=user_type)
    return redirect(url_for('login'))


@app.route('/book/<int:book_id>', methods=['GET', 'POST'])
def book_details(book_id):
    db = get_db()
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    user_type = 'User'
    if 'email' in session:
        logged_in = True
        email = session['email']
        cur.execute(f" SELECT Usr_Type FROM Users WHERE Email = ?", (session['email'],))
        user_type = cur.fetchone()[0]
        cur.execute("SELECT Usr_ID, Usr_Name FROM Users WHERE Email = ?", (email,))
        user = cur.fetchone()
        user_name = user[1]
        user_name = user_name.replace(' ', '_')
        table_name = f"{user_name}_{user[0]}"
        cur.execute("SELECT * FROM Books WHERE Book_ID = ?", (book_id,))
        book = cur.fetchone()
        cur.execute(f'''SELECT Status, Downloaded FROM {table_name} WHERE Book_ID = {book_id} 
                        AND Req_ID = (SELECT MAX(Req_ID) FROM {table_name} WHERE Book_ID = {book_id})''')
        status_results = cur.fetchone()
        cur.row_factory = None
        if status_results is None:
            status = None
            downloaded = None
        else:
            downloaded = status_results[1]
            status = status_results[0]
        cur.execute(f'''SELECT Deadline FROM {table_name} WHERE Book_ID = {book_id}''')
        deadline = cur.fetchone()
        deadline = deadline[0] if deadline else None
        cur.execute(f'''SELECT Current_Page FROM {table_name} WHERE Book_ID = {book_id}''')
        current_page = cur.fetchone()
        if not current_page:
            current_page = 1
        else:
            current_page = current_page[0]
        cur.execute(f'''SELECT Comment FROM Requests WHERE Book_ID = {book_id} AND Usr_ID = {user[0]}''')
        comment = cur.fetchone()
        comment = comment[0] if comment else None
        cur.row_factory = sqlite3.Row
    else:
        logged_in = False
        cur.execute("SELECT * FROM Books WHERE Book_ID = ?", (book_id,))
        book = cur.fetchone()
        deadline = None
        status = None
        current_page = 1
        downloaded = None
        comment = None
    db.close()
    return render_template('book_details.html', user_type=user_type, book=book, status=status,
                           downloaded=downloaded, deadline=deadline, comment=comment,
                           logged_in=logged_in, current_page=current_page)


# Route to fetch book details based on name, author, and pages
@app.route('/editBooks', methods=['GET', 'POST'])
def get_book_details():
    db = get_db()
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    if 'email' in session:
        try:
            book_name = request.args.get('name')
            author_name = request.args.get('author')
            pages = request.args.get('pages')
            cur.execute("SELECT * FROM books WHERE B_Name = ? AND Auth_Name = ? AND No_of_Pages = ?",
                        (book_name, author_name, pages))
            details = cur.fetchone()
            db.close()
            if details:
                # Construct a dictionary of details
                book = dict(details)
                return jsonify(book), 200  # Return book details as JSON response
            else:
                return jsonify({'error': 'Book not found'}), 404  # Book not found error

        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return redirect(url_for('login'))


def is_whitespace_or_empty(s):
    return s is None or s.strip() == ''


@app.route('/updateBookDetails', methods=['POST'])
def update_book_details():
    if 'email' in session:
        email = session['email']
        if not bool(re.match(r'^[\w.-]+@[a-zA-Z0-9.-]+(\.[a-zA-Z]+)$', email)):
            return jsonify({'error': 'Invalid Email'}), 400
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (email,))
        user_type = cursor.fetchone()[0]
        if user_type != 'Librarian':
            return jsonify({'error': 'Please login as a Librarian'}), 403
        try:
            book_id = request.json.get('bookId')
            title = request.json.get('editBookTitle')
            author = request.json.get('editBookAuthor')
            genre = request.json.get('editBookGenre')
            pages = request.json.get('editBookPages')
            rated = request.json.get('editBookRated')
            release_date = request.json.get('editBookReleaseDate')
            availability = request.json.get('editBookAvailability')
            sec_id = request.json.get('editBookSecID')
            rating = request.json.get('editBookRating')
            price = request.json.get('editBookPrice')
            cover_page = request.json.get('editBookCoverPage')
            description = request.json.get('editBookDescription')
            pdf_link = request.json.get('editBookPDF')

            # Validate json data (perform necessary checks)
            if not all([title, author, genre, pages, rated, release_date, availability, sec_id, rating, price]):
                return jsonify({'error': 'All fields are required'}), 400
            if ((float(rating) < 0 or float(rating) > 5 or int(pages) < 0 or float(price) < 0
                    or rated not in ['E', 'PG', 'PG-13', 'R'])):
                return jsonify({'error': 'Invalid Data'}), 400
            if datetime.strptime(release_date, '%Y-%m-%d').date() > datetime.now().date():
                return jsonify({'error': 'Invalid Date of Release'}), 400
            if not cover_page.lower().endswith('.jpeg'):
                return jsonify({'error': 'Cover page URL must end with .jpeg'}), 400
            if not pdf_link.lower().endswith('.pdf'):
                return jsonify({'error': 'PDF URL must end with .pdf'}), 400
            if any(is_whitespace_or_empty(s) for s in [title, author, genre, cover_page, description, pdf_link]):
                return jsonify(
                    {'error': 'All string fields must be non-empty and cannot consist only of whitespace'}), 400
            cursor.execute("""
                UPDATE Books
                SET B_Name = ?, Auth_Name = ?, Genre = ?, No_of_Pages = ?,
                    Content_Rated = ?, Date_of_Release = ?, Availability = ?,
                    Sec_ID = ?, Rating = ?, Price = ?, Cover_Page = ?,
                    Description = ?, PDF = ?
                WHERE Book_ID = ?
            """, (title, author, genre, pages, rated, release_date, availability,
                  sec_id, rating, price, cover_page, description, pdf_link, book_id))
            db.commit()
            db.close()
            return jsonify({'message': 'Book details updated successfully'}), 200
        except Exception as e:
            return jsonify({'error': 'Failed to update book details'}), 500
    return redirect(url_for('login'))


@app.route('/deleteBook', methods=['POST'])
def delete_book():
    if 'email' in session:
        email = session['email']
        if not bool(re.match(r'^[\w.-]+@[a-zA-Z0-9.-]+(\.[a-zA-Z]+)$', email)):
            return jsonify({'error': 'Invalid Email'}), 400
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (email,))
        user_type = cursor.fetchone()[0]
        if user_type != 'Librarian':
            return jsonify({'error': 'Please login as a Librarian'}), 403
        try:
            name = request.json.get('bookName')
            author = request.json.get('authorName')
            pages = request.json.get('pages')
            if (name.strip() == '' or author.strip() == '' or not name.isalnum() or
                    not author.isalnum() or pages is None or pages < 0):
                return jsonify({'error': 'All fields are required'}), 400
            cursor.execute('DELETE FROM Books WHERE B_Name = ? AND Auth_Name = ? AND No_of_Pages = ?', (name, author, pages))
            db.commit()
            db.close()
            return jsonify({'message': 'Book deleted successfully!'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return redirect(url_for('login'))


@app.route('/requests')
def get_requests():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    email = session['email']
    db = get_db()
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    cur.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (email,))
    user_type = cur.fetchone()
    if not user_type or user_type['Usr_Type'] != 'Librarian':
        return jsonify({'error': 'Please login as a Librarian'}), 403
    request_type = request.args.get('type')
    if not request_type:
        return jsonify({'error': 'Missing request type parameter'}), 400
    cur.execute("SELECT Req_ID, Usr_ID, Book_ID, Req_Date FROM requests WHERE Status = ?", (request_type,))
    requests = cur.fetchall()
    requests = [dict(row) for row in requests]
    for req in requests:
        cur.execute("SELECT Usr_Name, Age FROM Users WHERE Usr_ID = ?", (req['Usr_ID'],))
        user_info = cur.fetchone()
        if user_info:
            req['Usr_Name'] = user_info['Usr_Name']
            req['Age'] = user_info['Age']
        cur.execute("SELECT B_Name, Auth_Name, Content_Rated FROM Books WHERE Book_ID = ?", (req['Book_ID'],))
        book_info = cur.fetchone()
        if book_info:
            req['B_Name'] = book_info['B_Name']
            req['Auth_Name'] = book_info['Auth_Name']
            req['Content_Rated'] = book_info['Content_Rated']
    db.close()
    return jsonify(requests)


@app.route('/process_request', methods=['POST'])
def process_request():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    request_id = request.args.get('id')
    action = request.args.get('action')
    if action not in ['accept', 'deny']:
        return jsonify({'error': 'Invalid action specified'}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (session['email'],))
    user_type = cur.fetchone()[0]
    if user_type != 'Librarian':
        return jsonify({'error': 'Please login as a Librarian'}), 403
    cur.execute("SELECT Usr_ID FROM requests WHERE Req_ID = ?", (request_id,))
    usr_id = cur.fetchone()[0]
    cur.execute("SELECT Usr_Name FROM Users WHERE Usr_ID = ?", (usr_id,))
    usr_name = cur.fetchone()[0]
    usr_name = usr_name.replace(' ', '_')
    table_name = f"{usr_name}_{usr_id}"
    cur.row_factory = sqlite3.Row
    if action == 'accept':
        cur.execute("UPDATE requests SET Status = 'Accepted' WHERE Req_ID = ?", (request_id,))
        current_date = datetime.now().date()
        deadline_date = current_date + timedelta(days=60)
        sql = f"UPDATE {table_name} SET Status = 'Reading', Date_of_Issue = ?, Deadline = ? WHERE Req_ID = ?"
        cur.execute(sql, (current_date, deadline_date, request_id))
    elif action == 'deny':
        cur.execute("UPDATE requests SET Status = 'Denied' WHERE Req_ID = ?", (request_id,))
        cur.execute(f"UPDATE {table_name} SET Status = 'Declined' WHERE Req_ID = ?", (request_id,))
    db.commit()
    db.close()
    return jsonify({'message': f'Request {action}ed successfully'}), 200


@app.route('/user_status', methods=['GET'])
def get_user_status():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    email = session['email']
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (email,))
    user_type = cur.fetchone()[0]
    if not user_type or user_type != 'Librarian':
        return jsonify({'error': 'Please login as a Librarian'}), 403
    user_id = request.args.get('id')
    cur.execute("SELECT Usr_Name FROM Users WHERE Usr_ID = ?", (user_id,))
    user_name = cur.fetchone()[0]
    if not user_name:
        return jsonify({'error': 'User not found'}), 404
    user_name = user_name.replace(' ', '_')
    table_name = f"{user_name}_{user_id}"
    cur.row_factory = sqlite3.Row
    cur.execute(f"SELECT * FROM {table_name} where Status = 'Reading'")
    reading_books = cur.fetchall()
    reading_books = [dict(row) for row in reading_books]
    cur.execute(f"SELECT Book_ID, B_Name, Auth_Name, No_of_Pages FROM Books WHERE Book_ID IN "
                f"(SELECT Book_ID FROM {table_name} WHERE Status = 'Reading')")
    book_info = cur.fetchall()
    book_info = [dict(row) for row in book_info]
    book_info_mapping = {book['Book_ID']: {'B_Name': book['B_Name'], 'Auth_Name': book['Auth_Name'],
                                           'No_of_Pages': book['No_of_Pages']} for book in book_info}
    for book in reading_books:
        book_id = book['Book_ID']
        if book_id in book_info_mapping:
            book['Book_Name'] = book_info_mapping[book_id]['B_Name']
            book['Author_Name'] = book_info_mapping[book_id]['Auth_Name']
            book['No_of_Pages'] = book_info_mapping[book_id]['No_of_Pages']
        else:
            book['Book_Name'] = 'Unknown'
            book['Author_Name'] = 'Unknown'
            book['No_of_Pages'] = 'Unknown'
    db.close()
    print(reading_books)
    return jsonify({'booksInUse': reading_books}), 200


@app.route('/revoke_book', methods=['POST'])
def revoke_book():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    userId = data.get('userId')
    bookId = data.get('bookId')
    print(userId, bookId)
    if not userId or not bookId:
        return jsonify({'error': 'Invalid request data'}), 400
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT Usr_Type FROM Users WHERE Email = ?", (session['email'],))
        usr_type = cursor.fetchone()[0]
        if usr_type != 'Librarian':
            return jsonify({'error': 'Please login as a Librarian'}), 403
        cursor.execute("SELECT Usr_Name, Usr_Type FROM Users WHERE Usr_ID = ?", (userId,))
        usr_name, usr_type = cursor.fetchone()
        usr_name = usr_name.replace(' ', '_')
        table_name = f"{usr_name}_{userId}"
        cursor.execute(f"UPDATE {table_name} SET Status = 'Revoked' WHERE Book_ID = ?", (bookId,))
        db.commit()
        db.close()
        return jsonify({'message': 'Book revoked successfully'}), 200
    except sqlite3.Error as e:
        print('SQLite error:', e)
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as ex:
        print('Exception:', ex)
        return jsonify({'error': 'An unexpected error occurred'}), 500


@app.route('/request', methods=['GET', 'POST'])
def request_book():
    if 'email' in session:
        book_id = request.args.get('book_id')
        email = session['email']
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT Usr_ID, Usr_Name FROM Users WHERE Email = ?", (email,))
        user = cur.fetchone()
        user_name = user[1]
        user_name = user_name.replace(' ', '_')
        table_name = f"{user_name}_{user[0]}"
        date = datetime.now().date()
        cur.execute("SELECT COUNT(*) FROM {} WHERE STATUS IN ('Reading', 'Requested')".format(table_name))
        reading_count = cur.fetchone()[0]
        cur.row_factory = sqlite3.Row
        cur.execute("Select * from Books where Book_ID = ?", (book_id,))
        book = cur.fetchone()
        cur.row_factory = None
        if reading_count >= 5:
            return render_template('book_details.html', book=book, status='None', logged_in=True,
                                   error_message='You can only request 5 books at a time', current_page=1)
        cur.execute("INSERT INTO Requests (Book_ID, Usr_ID, Req_Date) VALUES (?, ?, ?)",
                    (book_id, user[0], date))
        db.commit()
        req_id = cur.lastrowid
        cur.execute(f"SELECT Req_ID FROM {table_name} WHERE Book_ID = {book_id}")
        req = cur.fetchone()
        if not req:
            query = f"INSERT INTO {table_name} (Req_ID, Book_ID, Status) VALUES (?, ?, ?)"
            cur.execute(query, (req_id, book_id, 'Requested'))
            db.commit()
        else:
            query = f"UPDATE {table_name} SET Req_ID = ?, Status = ? WHERE Book_ID = ?"
            cur.execute(query, (req_id, 'Requested', book_id))
            db.commit()
        db.close()
        return render_template('book_details.html', book=book, status='Requested', logged_in=True, current_page=1)
    return redirect(url_for('login'))


@app.route('/return', methods=['GET', 'POST'])
def return_book():
    if 'email' in session:
        book_id = request.args.get('book_id')
        email = session['email']
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT Usr_ID, Usr_Name FROM Users WHERE Email = ?", (email,))
        user = cur.fetchone()
        if user:
            user_name = user[1]
            user_name = user_name.replace(' ', '_')
            table_name = f"{user_name}_{user[0]}"
            date = datetime.now().date()
            cur.execute(f"UPDATE {table_name} SET Status = 'Returned', Date_of_Return = ? WHERE Book_ID = ?",
                        (date, book_id))
            db.commit()
            cur.row_factory = sqlite3.Row
            cur.execute("SELECT * FROM Books WHERE Book_ID = ?", (book_id,))
            book = cur.fetchone()
            db.close()
            return render_template('book_details.html', current_page=1, book=book, status='Returned', logged_in=True)
    return redirect(url_for('login'))


@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    if 'email' in session:
        email = session['email']
        rating = request.json.get('rating')
        feedback = request.json.get('feedback')
        book_id = request.json.get('book_id')
        if rating is not None:
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT Usr_ID, Usr_Name FROM Users WHERE Email = ?", (email,))
            user = cur.fetchone()
            user_name = user[1]
            user_name = user_name.replace(' ', '_')
            table_name = f"{user_name}_{user[0]}"
            if feedback == '':
                feedback = 'NULL'
            cur.execute(f"Update {table_name} SET Rating = ?, Feedback = ? "
                        f"WHERE Book_ID = ?", (rating, feedback, book_id))
            db.commit()
            db.close()
            return jsonify({'message': 'Feedback submitted successfully'}), 200
        else:
            return jsonify({'error': 'Invalid rating or feedback'}), 420
    else:
        return jsonify({'error': 'User not logged in'}), 401


@app.route('/update_page', methods=['POST'])
def update_page():
    data = request.get_json()
    if 'email' in session and data:
        email = session['email']
        book_id = data.get('book_id')
        page = data.get('page')
        try:
            db = get_db()
            cur = db.cursor()
            cur.row_factory = sqlite3.Row
            cur.execute("SELECT Usr_ID, Usr_Name FROM Users WHERE Email = ?", (email,))
            user = cur.fetchone()
            if page:
                user = dict(user)
                user['Usr_Name'] = user['Usr_Name'].replace(' ', '_')
                table_name = f"{user['Usr_Name']}_{user['Usr_ID']}"
                cur.execute(f"UPDATE {table_name} SET Current_Page = ? WHERE Book_ID = ?", (page, book_id))
                db.commit()
                db.close()
                return jsonify({'message': 'Page updated successfully'}), 200
            else:
                return jsonify({'error': 'Invalid page number'}), 420
        except sqlite3.Error as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'Invalid data or session'}), 400


@app.route('/download_pdf', methods=['GET'])
def download_pdf():
    book_id = request.args.get('book_id')
    if 'email' not in session:
        return redirect(url_for('login'))
    if not book_id:
        return "Book ID parameter is missing", 400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT PDF FROM Books WHERE Book_ID = ?", (book_id,))
    pdf_filename = cur.fetchone()[0]
    if not pdf_filename:
        return "PDF file not found", 404

    pdf_directory = os.path.join(app.root_path, 'static', 'PDFs')
    pdf_path = os.path.join(pdf_directory, pdf_filename)
    if not os.path.isfile(pdf_path):
        return "Error: PDF file not found", 404
    cur.execute("SELECT Usr_ID, Usr_Name FROM Users WHERE Email = ?", (session['email'],))
    user = cur.fetchone()
    user_name = user[1]
    user_name = user_name.replace(' ', '_')
    table_name = f"{user_name}_{user[0]}"
    cur.execute(f"UPDATE {table_name} SET Downloaded = 'Yes', Download_date = ? "
                f"WHERE Book_ID = ?", (datetime.now().date(), book_id))
    db.commit()
    db.close()
    return send_from_directory(pdf_directory, pdf_filename, as_attachment=True)


@app.route('/search', methods=['POST'])
def search():
    query = request.form['query']
    filtered_books = []
    filtered_auth = []
    filtered_sec = []
    clear = 0
    if query != '':
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT B_Name FROM books WHERE B_Name LIKE ? ORDER BY Rating DESC", ('%' + query + '%',))
        filtered_books = [i[0] for i in cur.fetchall()]
        cur.execute("SELECT DISTINCT Auth_Name FROM books WHERE Auth_Name LIKE ? ORDER BY Rating DESC",
                    ('%' + query + '%',))
        filtered_auth = [i[0] for i in cur.fetchall()]
        cur.execute("SELECT Sec_Name FROM sections WHERE Sec_Name LIKE ? ORDER BY Sec_Name DESC", ('%' + query + '%',))
        filtered_sec = [i[0] for i in cur.fetchall()]
        if ' ' not in query:
            filtered_books = [book for book in filtered_books
                              if any(str(word).lower().startswith(query.lower()) for word in book.split())]
            filtered_auth = [auth for auth in filtered_auth
                             if any(str(word).lower().startswith(query.lower()) for word in auth.split())]
            filtered_sec = [sec for sec in filtered_sec
                            if any(str(word).lower().startswith(query.lower()) for word in sec.split())]
        db.close()
    else:
        clear = 1
    return jsonify(results=filtered_books[0:5], authors=filtered_auth[0:5], sections=filtered_sec[0:5], clear=clear)


@app.route('/delete_account', methods=['GET'])
def delete_account():
    if 'email' in session:
        email = session['email']
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT Usr_ID, Usr_name FROM Users WHERE Email = ?", (email,))
        user = cur.fetchone()
        user_name = user[1]
        user_name = user_name.replace(' ', '_')
        table_name = f"{user_name}_{user[0]}"
        cur.execute("DELETE FROM Requests WHERE Usr_ID = ?", (user[0],))
        db.commit()
        cur.execute("DELETE FROM Users WHERE Email = ?", (email,))
        db.commit()
        cur.execute(f"DROP TABLE IF EXISTS {table_name}")
        db.close()
        session.clear()
        return redirect(url_for('login'))


@app.route('/logout', methods=['GET'])
def logout():
    if 'email' in session:
        db = get_db()
        cur = db.cursor()
        cur.execute('UPDATE Users SET Acc_Status = ? WHERE Email = ?', ('Inactive', session['email']))
        db.commit()
        cur.close()
        session.pop('email', None)
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)
