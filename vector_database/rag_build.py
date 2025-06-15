import mysql.connector
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import pandas as pd
import os

# Step 1: Connect to MySQL Database
def connect_to_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Passw0rd!",
        database="CulinaryAI"
    )

# Step 2: Get Non-ID Columns Dynamically
def get_non_id_columns(connection, table_name):
    cursor = connection.cursor()
    cursor.execute(f"SHOW COLUMNS FROM {table_name};")
    columns = cursor.fetchall()
    cursor.close()
    
    return [col[0] for col in columns if 'id' not in col[0].lower()]

# Step 3: Fetch Data from Table
def fetch_table_data(connection, table_name):
    cursor = connection.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {table_name};")
    data = cursor.fetchall()
    cursor.close()
    return data

# Step 4: Generate Text Embeddings
def generate_text_embeddings(data, text_columns, model):
    texts = [" ".join(str(row[col]) for col in text_columns if row[col]) for row in data]
    embeddings = model.encode(texts)
    return np.array(embeddings, dtype="float32"), texts

# Step 5: Process Tables and Store in a Single Index
def build_combined_faiss_index(tables, model_name="all-MiniLM-L6-v2"):
    model = SentenceTransformer(model_name)
    all_embeddings, all_metadata = [], []
    connection = connect_to_db()
    
    try:
        for table_name in tables:
            print(f"Processing table: {table_name}")
            data = fetch_table_data(connection, table_name)
            if not data:
                print(f"Table {table_name} is empty. Skipping.")
                continue

            non_id_columns = get_non_id_columns(connection, table_name)
            text_columns = [col for col in non_id_columns if isinstance(data[0].get(col), str)]
            embeddings, texts = generate_text_embeddings(data, text_columns, model)
            
            all_embeddings.append(embeddings)
            for i, row in enumerate(data):
                row_metadata = {col: row[col] for col in non_id_columns if col not in text_columns}
                row_metadata.update({"text": texts[i], "category": table_name})
                all_metadata.append(row_metadata)
    
    finally:
        connection.close()
    
    # Merge all embeddings
    all_embeddings = np.vstack(all_embeddings)
    
    # Create FAISS index
    d = all_embeddings.shape[1]
    index = faiss.IndexFlatL2(d)
    index = faiss.IndexIDMap(index)
    
    ids = np.arange(len(all_embeddings))
    index.add_with_ids(all_embeddings, ids)
    
    # Save index and metadata
    os.makedirs("vector_databasess", exist_ok=True)
    faiss.write_index(index, "vector_databasess/restaurant_data.index")
    pd.DataFrame(all_metadata).to_csv("vector_databasess/restaurant_data.csv", index=False)
    
    print("FAISS index and metadata saved.")

# Run the process
if __name__ == "__main__":
    tables = ["Menu", "GeneralInfo", "Reservations", "OrderTracking"]
    build_combined_faiss_index(tables)
