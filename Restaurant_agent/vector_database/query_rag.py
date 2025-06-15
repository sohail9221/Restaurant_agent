import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import pandas as pd

# Step 1: Load FAISS Index and Metadata
def load_faiss_and_metadata():
    index = faiss.read_index("vector_databasess/restaurant_data.index")
    metadata_df = pd.read_csv("vector_databasess/restaurant_data.csv")
    return index, metadata_df

# Step 2: Generate Query Embedding
def generate_query_embedding(query, model):
    return np.array(model.encode([query]), dtype="float32")

# Step 3: Search FAISS Index
def search_faiss_index(query_embedding, index, top_k=5):
    distances, indices = index.search(query_embedding, top_k)
    return distances, indices

# Step 4: Clean Metadata (Remove NaN values)
def clean_metadata(metadata):
    return {key: value for key, value in metadata.items() if pd.notna(value) and key != "category"}

# Step 5: Fetch Metadata for Top Results (with Optional Filtering)
def fetch_metadata_for_results(indices, metadata_df, category_filter=None):
    results_metadata = []
    
    for idx in indices[0]:
        result = metadata_df.iloc[idx].to_dict()
        
        # Apply category filtering
        if category_filter and result["category"] != category_filter:
            continue
        
        cleaned_result = clean_metadata(result)  # Remove NaN values
        results_metadata.append(cleaned_result)
    
    return results_metadata

# Step 6: Query with Filtering Option
def query_faiss_index(query, top_k=5, category_filter=None, model_name="all-MiniLM-L6-v2"):
    index, metadata_df = load_faiss_and_metadata()
    model = SentenceTransformer(model_name)
    
    query_embedding = generate_query_embedding(query, model)
    distances, indices = search_faiss_index(query_embedding, index, top_k)
    
    results_metadata = fetch_metadata_for_results(indices, metadata_df, category_filter)
    return distances, results_metadata

# Example Usage
# if __name__ == "__main__":
#     query = "Do you have biryani or something like that like rice?"
    
#     # Example: Get results only from the 'Menu' category
#     distances, results_metadata = query_faiss_index(query, top_k=3)
    
#     print("\nTop Results:")
#     for i, result in enumerate(results_metadata):
#         print(f"\nResult {i+1}: Distance: {distances[0][i]}")
#         print(result)  # Cleaned output without NaN values
