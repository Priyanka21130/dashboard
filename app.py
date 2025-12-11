import streamlit as st
import pandas as pd
import pygsheets
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
import io
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import requests

# ===================== CONFIG =====================
SPREADSHEET_ID = "1dWv4kVugXNFQ2NaodZkawaXRglqRJOWR"
SHEET_GID = "840573777"
PROPOSAL_GID = "1356001164"
SHEET_NAME = "Pri Payment"
PROPOSAL_SHEET_NAME = "Proposals"
SERVICE_FILE = "service_account.json"

st.set_page_config(page_title="Payment Dashboard", layout="wide")

# ===================== AUTO REFRESH SETTINGS =====================
st.sidebar.subheader("🔄 Auto Refresh Settings")

enable_auto = st.sidebar.checkbox("Enable Auto Refresh", value=False)
interval = st.sidebar.number_input("Refresh Interval (seconds)", 10, 300, 60)

if enable_auto:
    st_autorefresh(interval=interval * 1000, key="auto_refresh")

# ===================== CUSTOM CSS FOR DARK THEME =====================
st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; background-color: #0E1117; }
    .metric-card { background: linear-gradient(135deg, #1E293B 0%, #334155 100%); padding: 1.5rem; border-radius: 12px; border: 1px solid #374151; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3); margin-bottom: 1rem; }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 6px 8px -1px rgba(0, 0, 0, 0.4); }
    .metric-title { font-size: 0.9rem; font-weight: 600; color: #94A3B8; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-value { font-size: 1.8rem; font-weight: 700; color: #FFFFFF; margin-bottom: 0; }
    .section-header { font-size: 1.4rem; font-weight: 700; color: #FFFFFF; margin: 2rem 0 1rem 0; padding-bottom: 0.5rem; border-bottom: 2px solid #374151; }
    .status-summary { background: #1E293B; padding: 1.5rem; border-radius: 12px; border: 1px solid #374151; margin-bottom: 1rem; }
    .status-item { display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #374151; }
    .status-item:last-child { border-bottom: none; }
    .chart-container { background: #1E293B; padding: 1.5rem; border-radius: 12px; border: 1px solid #374151; margin-bottom: 1rem; }
    .kpi-row { display: flex; gap: 1rem; margin-bottom: 2rem; }
    /* Proposal status colors */
    .status-approved { color: #10B981; font-weight: bold; }
    .status-pending { color: #F59E0B; font-weight: bold; }
    .status-rejected { color: #EF4444; font-weight: bold; }
    .status-review { color: #8B5CF6; font-weight: bold; }
    .status-ok { color: #10B981; font-weight: bold; }
    .status-drop { color: #EF4444; font-weight: bold; }
    .status-ongoing { color: #3B82F6; font-weight: bold; }
    .status-others { color: #6B7280; font-weight: bold; }
    .status-followup { color: #F59E0B; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ===================== DATA LOADING FUNCTIONS =====================
def clean_colname(x):
    x = str(x).strip().lower()
    x = re.sub(r"[^0-9a-zA-Z_ ]", "", x)
    x = x.replace(" ", "_")
    return x if x else "col"

def safe_num(v):
    """Enhanced number conversion for Indian currency format"""
    try:
        if pd.isna(v) or v == "" or str(v).strip() == "":
            return 0.0
        
        # Convert to string and clean
        v_str = str(v).strip()
        
        # Remove currency symbols, commas, and spaces
        v_clean = re.sub(r'[₹$,\\s]', '', v_str)
        
        # Handle negative numbers in parentheses
        if v_clean.startswith('(') and v_clean.endswith(')'):
            v_clean = '-' + v_clean[1:-1]
        
        # Convert to float
        return float(v_clean) if v_clean else 0.0
        
    except Exception as e:
        return 0.0

def parse_date(v):
    try:
        return pd.to_datetime(v, dayfirst=True, errors="coerce")
    except:
        return pd.NaT

# ===================== LOAD PAYMENT DATA VIA SERVICE ACCOUNT =====================
@st.cache_data(ttl=120)
def load_via_service():
    try:
        gc = pygsheets.authorize(service_file=SERVICE_FILE)
        
        # Open by ID (most reliable method)
        sh = gc.open_by_key(SPREADSHEET_ID)
        st.sidebar.success(f"📊 Opened: {sh.title}")
        
        # Try to get the specific sheet by GID
        try:
            wks = sh.worksheet(property='id', value=SHEET_GID)
            st.sidebar.info(f"📑 Using sheet: {wks.title} (GID: {SHEET_GID})")
        except:
            # Fallback to first sheet
            wks = sh[0]
            st.sidebar.warning(f"⚠️ Using first sheet: {wks.title}")
        
        # Get all data
        data = wks.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            st.sidebar.warning("📭 Loaded empty dataframe")
            return None
            
        st.sidebar.success(f"✅ Loaded {len(df)} records via Service Account")
        return df
        
    except Exception as e:
        st.sidebar.error(f"❌ Service Account failed: {str(e)}")
        return None

# ===================== LOAD PROPOSAL DATA =====================
@st.cache_data(ttl=120)
def load_proposal_data():
    """Load proposal data from Google Sheets"""
    try:
        gc = pygsheets.authorize(service_file=SERVICE_FILE)
        sh = gc.open_by_key(SPREADSHEET_ID)
        st.sidebar.success(f"📊 Opened spreadsheet: {sh.title}")

        # Debug: List all worksheets
        st.sidebar.info(f"📑 Available worksheets in '{sh.title}':")
        worksheets = sh.worksheets()
        for i, ws in enumerate(worksheets):
            st.sidebar.info(f"  {i+1}. {ws.title} (ID: {ws.id})")
        
        # Try to get proposal sheet by GID
        try:
            st.sidebar.info(f"🔍 Looking for sheet with GID: {PROPOSAL_GID}")
            proposal_wks = sh.worksheet(property='id', value=PROPOSAL_GID)
            st.sidebar.success(f"✅ Found proposal sheet: {proposal_wks.title} (GID: {PROPOSAL_GID})")
        except Exception as e:
            st.sidebar.warning(f"⚠️ Could not find sheet by GID {PROPOSAL_GID}: {str(e)}")
            
            # Fallback to sheet name
            try:
                st.sidebar.info(f"🔍 Looking for sheet by name: {PROPOSAL_SHEET_NAME}")
                proposal_wks = sh.worksheet_by_title(PROPOSAL_SHEET_NAME)
                st.sidebar.success(f"✅ Found proposal sheet by name: {proposal_wks.title}")
            except Exception as e2:
                st.sidebar.error(f"❌ Could not find proposal sheet by name '{PROPOSAL_SHEET_NAME}': {str(e2)}")
                
                # Try to find any sheet with "proposal" in the name
                st.sidebar.info("🔍 Searching for sheets with 'proposal' in name...")
                matching_sheets = [ws for ws in worksheets if 'proposal' in ws.title.lower()]
                if matching_sheets:
                    proposal_wks = matching_sheets[0]
                    st.sidebar.success(f"✅ Using sheet: {proposal_wks.title}")
                else:
                    st.sidebar.error("❌ No proposal sheet found")
                    return None
        
        # Get all proposal data
        st.sidebar.info("📥 Fetching proposal data...")
        proposal_data = proposal_wks.get_all_records()
        proposal_df = pd.DataFrame(proposal_data)
        
        if proposal_df.empty:
            st.sidebar.warning("📭 Loaded empty proposal dataframe")
            return None
            
        st.sidebar.success(f"✅ Loaded {len(proposal_df)} proposal records")
        
        # Debug: Show column names
        st.sidebar.info("📋 Proposal columns found:")
        for col in proposal_df.columns:
            st.sidebar.info(f"  - {col}")
            
        return proposal_df
        
    except Exception as e:
        st.sidebar.error(f"❌ Failed to load proposal data: {str(e)}")
        return None

# ===================== ENHANCED CSV LOADING FOR PAYMENT DATA =====================
@st.cache_data(ttl=120)
def load_via_csv():
    """Load payment data via CSV export"""
    try:
        st.sidebar.info("🔄 Trying to load payment data via CSV export...")
        
        # Try different CSV URL formats
        csv_urls = [
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={SHEET_GID}",
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={SHEET_GID}",
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv",
        ]
        
        for i, csv_url in enumerate(csv_urls):
            try:
                st.sidebar.info(f"  Trying URL {i+1}...")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                import time
                csv_url += f"&t={int(time.time())}"
                
                response = requests.get(csv_url, headers=headers, timeout=30)
                response.raise_for_status()
                
                # Try different encodings
                encodings = ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1']
                
                for encoding in encodings:
                    try:
                        df = pd.read_csv(
                            io.StringIO(response.text), 
                            encoding=encoding,
                            skip_blank_lines=True,
                            na_filter=False,
                            dtype=str,
                            thousands=',',
                            skipinitialspace=True
                        )
                        
                        df = df.dropna(how='all')
                        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
                        
                        if not df.empty and len(df.columns) > 1:
                            st.sidebar.success(f"✅ CSV loaded: {len(df)} records with encoding {encoding}")
                            return df
                            
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        continue
                        
            except Exception as e:
                st.sidebar.warning(f"  URL {i+1} failed: {str(e)}")
                continue
        
        return None
        
    except Exception as e:
        st.sidebar.error(f"❌ CSV Export failed: {str(e)}")
        return None

# ===================== ENHANCED CSV LOADING FOR PROPOSALS =====================
@st.cache_data(ttl=120)
def load_proposal_via_csv():
    """Alternative method to load proposal data via CSV export"""
    try:
        st.sidebar.info("🔄 Trying to load proposal data via CSV export...")
        
        # Try different CSV URL formats
        csv_urls = [
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={PROPOSAL_GID}",
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={PROPOSAL_GID}",
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv",
        ]
        
        for i, csv_url in enumerate(csv_urls):
            try:
                st.sidebar.info(f"  Trying URL {i+1}...")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                import time
                csv_url += f"&t={int(time.time())}"
                
                response = requests.get(csv_url, headers=headers, timeout=30)
                response.raise_for_status()
                
                # Try different encodings
                encodings = ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1']
                
                for encoding in encodings:
                    try:
                        df = pd.read_csv(
                            io.StringIO(response.text), 
                            encoding=encoding,
                            skip_blank_lines=True,
                            na_filter=False,
                            dtype=str,
                            thousands=',',
                            skipinitialspace=True
                        )
                        
                        df = df.dropna(how='all')
                        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
                        
                        if not df.empty and len(df.columns) > 1:
                            st.sidebar.success(f"✅ CSV loaded: {len(df)} records with encoding {encoding}")
                            return df
                            
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        continue
                        
            except Exception as e:
                st.sidebar.warning(f"  URL {i+1} failed: {str(e)}")
                continue
        
        return None
        
    except Exception as e:
        st.sidebar.error(f"❌ CSV Export failed: {str(e)}")
        return None

# ===================== DEMO DATA (Fallback for Payment only) =====================
def load_demo_data():
    """Load demo data matching your expected structure"""
    demo_data = {
        'Unit Name': ['Unit A', 'Unit B', 'Unit C', 'Unit D'],
        'Work Order No': ['WO001', 'WO002', 'WO003', 'WO004'],
        'Order Amount': ['79,290,940.00', '65,000,000.00', '45,500,000.00', '38,750,000.00'],
        'Final Amount': ['91,102,303.30', '75,000,000.00', '52,500,000.00', '44,750,000.00'],
        'Payment Received': ['36,923,263.30', '30,000,000.00', '25,000,000.00', '18,500,000.00'],
        'Pending Amount': ['54,179,040.00', '45,000,000.00', '27,500,000.00', '26,250,000.00'],
        'Payment Mode': ['Online', 'Cash', 'Cheque', 'Cash and Online'],
        'Work Status': ['Completed', 'In Progress', 'Pending', 'Completed'],
        'Date': ['01/01/2024', '15/01/2024', '20/01/2024', '25/01/2024']
    }
    return pd.DataFrame(demo_data)

# ===================== IMPROVED DATA PROCESSING =====================
def process_raw_data(df):
    """Process and clean the raw data with enhanced CSV handling"""
    # Create a clean copy
    df_clean = df.copy()
    
    # Clean column names
    df_clean.columns = [clean_colname(c) for c in df_clean.columns]
    
    # Debug info
    with st.sidebar.expander("🔍 Payment Debug Info"):
        st.write("Original columns:", list(df.columns))
        st.write("Cleaned columns:", list(df_clean.columns))
        st.write("Data shape:", df_clean.shape)
        if not df_clean.empty:
            st.write("First 2 rows sample:", df_clean.head(2).to_dict('records'))
    
    # Enhanced column mapping
    column_mapping = {
        'unit_name': ['unit_name', 'unit', 'unitname', 'name', 'client', 'customer'],
        'work_order_no': ['work_order_no', 'work_order', 'wo_no', 'order_no', 'workorder', 'wo_number'],
        'order_amount': ['order_amount', 'order', 'amount', 'order_amt', 'initial_amount', 'quoted_amount'],
        'final_amount': ['final_amount', 'final', 'final_amt', 'total_amount', 'grand_total', 'invoice_amount'],
        'payment_received': ['payment_received', 'received', 'paid', 'payment_received', 'amount_received', 'paid_amount'],
        'pending_amount': ['pending_amount', 'pending', 'balance', 'due_amount', 'outstanding', 'remaining'],
        'payment_mode': ['payment_mode', 'mode', 'payment_type', 'type', 'payment_method'],
        'work_status': ['work_status', 'status', 'job_status', 'project_status', 'completion_status'],
        'date': ['date', 'p_date', 'payment_date', 'transaction_date', 'invoice_date', 'entry_date']
    }
    
    # Apply column mapping with feedback
    mapped_count = 0
    for standard_name, possible_names in column_mapping.items():
        for possible_name in possible_names:
            if possible_name in df_clean.columns and standard_name not in df_clean.columns:
                df_clean.rename(columns={possible_name: standard_name}, inplace=True)
                mapped_count += 1
                st.sidebar.info(f"📝 Mapped '{possible_name}' → '{standard_name}'")
                break
    
    # Ensure required columns exist
    required_cols = ['order_amount', 'final_amount', 'payment_received']
    for col in required_cols:
        if col not in df_clean.columns:
            df_clean[col] = 0.0
            st.sidebar.warning(f"⚠️ Column '{col}' not found, using defaults")
    
    # Handle pending_amount separately
    if 'pending_amount' not in df_clean.columns:
        st.sidebar.info("🔄 'pending_amount' column not found, will calculate it")
        df_clean['pending_amount'] = 0.0
    
    # Enhanced numeric conversion with debugging
    numeric_cols = ['order_amount', 'final_amount', 'payment_received', 'pending_amount']
    conversion_debug = {}
    
    for col in numeric_cols:
        if col in df_clean.columns:
            # Store sample values for debugging
            original_samples = df_clean[col].head(3).tolist()
            
            # Apply conversion
            df_clean[col] = df_clean[col].apply(safe_num)
            
            # Store converted samples
            converted_samples = df_clean[col].head(3).tolist()
            conversion_debug[col] = {
                'original': original_samples,
                'converted': converted_samples,
                'total': df_clean[col].sum()
            }
    
    # Show conversion debug
    with st.sidebar.expander("💰 Number Conversion Debug"):
        for col, debug_info in conversion_debug.items():
            st.write(f"**{col}:**")
            st.write(f"  Original: {debug_info['original']}")
            st.write(f"  Converted: {debug_info['converted']}")
            st.write(f"  Total: ₹ {debug_info['total']:,.2f}")
    
    # Calculate pending amount (CRITICAL FIX)
    if all(col in df_clean.columns for col in ['final_amount', 'payment_received']):
        calculated_pending = df_clean['final_amount'] - df_clean['payment_received']
        
        # Always use calculated pending for accuracy
        df_clean['pending_amount'] = calculated_pending.clip(lower=0)
        
        # Show validation
        existing_total = conversion_debug.get('pending_amount', {}).get('total', 0)
        calculated_total = calculated_pending.sum()
        
        st.sidebar.info(f"💰 Pending Amount Validation:")
        st.sidebar.info(f"   CSV Provided: ₹ {existing_total:,.2f}")
        st.sidebar.info(f"   Calculated: ₹ {calculated_total:,.2f}")
        
        if abs(existing_total - calculated_total) > 100:
            st.sidebar.success("✅ Using calculated pending amounts for accuracy")
    
    # Process work status
    if 'work_status' not in df_clean.columns:
        df_clean['work_status'] = 'Unknown'
    else:
        df_clean['work_status'] = df_clean['work_status'].fillna('Unknown').astype(str).str.strip().str.title()
    
    # Process payment mode
    if 'payment_mode' not in df_clean.columns:
        df_clean['payment_mode'] = 'Unknown'
    else:
        df_clean['payment_mode'] = df_clean['payment_mode'].fillna('Unknown').astype(str).str.strip().str.title()
    
    # Process dates
    date_cols = ['date', 'p_date', 'payment_date']
    for date_col in date_cols:
        if date_col in df_clean.columns:
            df_clean['payment_date'] = df_clean[date_col].apply(parse_date)
            break
    else:
        df_clean['payment_date'] = pd.NaT
    
    df_clean['year'] = df_clean['payment_date'].dt.year.fillna(datetime.now().year).astype(int)
    
    # Final summary
    st.sidebar.success(f"✅ Processed {len(df_clean)} records")
    st.sidebar.info(f"📊 Final Totals:")
    st.sidebar.info(f"   Order: ₹ {df_clean['order_amount'].sum():,.2f}")
    st.sidebar.info(f"   Final: ₹ {df_clean['final_amount'].sum():,.2f}")
    st.sidebar.info(f"   Received: ₹ {df_clean['payment_received'].sum():,.2f}")
    st.sidebar.info(f"   Pending: ₹ {df_clean['pending_amount'].sum():,.2f}")
    
    return df_clean

def process_proposal_data(proposal_df):
    """Process and clean proposal data based on your sheet structure"""
    if proposal_df.empty:
        return proposal_df
    
    df_clean = proposal_df.copy()
    
    # Clean column names
    df_clean.columns = [clean_colname(c) for c in df_clean.columns]
    
    # Show debug info in main area for better visibility
    st.sidebar.subheader("📋 Proposal Data Processing")
    with st.sidebar.expander("🔍 Proposal Debug Info", expanded=True):
        st.write("**Raw columns found:**", list(proposal_df.columns))
        st.write("**Cleaned columns:**", list(df_clean.columns))
        st.write("**Data shape:**", df_clean.shape)
        if not df_clean.empty:
            st.write("**First 3 rows:**")
            st.dataframe(df_clean.head(3))
            st.write("**Column types:**")
            st.write(df_clean.dtypes)
    
    # Enhanced column mapping for proposals
    column_mapping = {
        's_no': ['s_no', 'sno', 'sl_no', 'serial_no', 'serial_number'],
        'year': ['year', 'yr', 'year_'],
        'date': ['date', 'proposal_date', 'submission_date'],
        'wo_date': ['wo_date', 'work_order_date', 'order_date'],
        'no': ['no', 'wo_no', 'work_order_no', 'order_no'],
        'name': ['name', 'client_name', 'company', 'customer', 'client'],
        'industry_type': ['industry_type', 'industry', 'business_type', 'sector'],
        'district': ['district', 'location', 'city_district', 'area'],
        'scope_of_work': ['scope_of_work', 'scope', 'work_scope', 'description'],
        'type': ['type', 'proposal_type', 'category'],
        'source': ['source', 'lead_source', 'referral_source'],
        'status': ['status', 'proposal_status', 'current_status'],
        'refrence_no': ['refrence_no', 'reference_no', 'ref_no', 'proposal_no'],
        'contact_person': ['contact_person', 'contact', 'person', 'representative'],
        'amount': ['amount', 'proposal_amount', 'value', 'quoted_amount'],
        'present_status': ['present_status', 'current_status', 'latest_status', 'status_update']
    }
    
    # Apply column mapping with feedback
    mapped_count = 0
    for standard_name, possible_names in column_mapping.items():
        for possible_name in possible_names:
            if possible_name in df_clean.columns and standard_name not in df_clean.columns:
                df_clean.rename(columns={possible_name: standard_name}, inplace=True)
                mapped_count += 1
                st.sidebar.info(f"📝 Mapped '{possible_name}' → '{standard_name}'")
                break
    
    # Process amount column
    if 'amount' in df_clean.columns:
        st.sidebar.info(f"💰 Processing amount column...")
        df_clean['amount'] = df_clean['amount'].apply(safe_num)
        st.sidebar.success(f"✅ Total proposal value: ₹ {df_clean['amount'].sum():,.2f}")
    else:
        st.sidebar.warning("⚠️ Amount column not found in proposal data")
        df_clean['amount'] = 0.0
    
    # Process dates
    date_columns = ['date', 'wo_date']
    for date_col in date_columns:
        if date_col in df_clean.columns:
            st.sidebar.info(f"📅 Processing {date_col} column...")
            df_clean[date_col] = df_clean[date_col].apply(parse_date)
    
    # Process year (convert to integer if possible)
    if 'year' in df_clean.columns:
        try:
            df_clean['year'] = pd.to_numeric(df_clean['year'], errors='coerce').fillna(0).astype(int)
        except:
            pass
    
    # Clean status columns
    status_columns = ['status', 'present_status']
    for status_col in status_columns:
        if status_col in df_clean.columns:
            df_clean[status_col] = df_clean[status_col].fillna('Unknown').astype(str).str.strip().str.title()
    
    # Clean other text columns
    text_columns = ['name', 'industry_type', 'district', 'scope_of_work', 'type', 'source', 'refrence_no', 'contact_person']
    for col in text_columns:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].fillna('').astype(str).str.strip()
    
    # Final summary
    st.sidebar.success(f"✅ Processed {len(df_clean)} proposal records")
    
    return df_clean

# ===================== PROPOSAL ANALYTICS FUNCTIONS =====================
def get_proposal_insights(proposal_df):
    """Generate insights from proposal data"""
    insights = {}
    
    if proposal_df.empty:
        return insights
    
    # Total proposals
    insights['total_proposals'] = len(proposal_df)
    
    # Total proposal value
    if 'amount' in proposal_df.columns:
        insights['total_value'] = proposal_df['amount'].sum()
    
    # Status distribution
    if 'status' in proposal_df.columns:
        status_counts = proposal_df['status'].value_counts()
        insights['status_distribution'] = status_counts.to_dict()
    
    # Present status distribution
    if 'present_status' in proposal_df.columns:
        present_status_counts = proposal_df['present_status'].value_counts()
        insights['present_status_distribution'] = present_status_counts.to_dict()
    
    # Industry type distribution
    if 'industry_type' in proposal_df.columns:
        industry_counts = proposal_df['industry_type'].value_counts()
        insights['industry_distribution'] = industry_counts.to_dict()
    
    # District distribution
    if 'district' in proposal_df.columns:
        district_counts = proposal_df['district'].value_counts()
        insights['district_distribution'] = district_counts.to_dict()
    
    # Source distribution
    if 'source' in proposal_df.columns:
        source_counts = proposal_df['source'].value_counts()
        insights['source_distribution'] = source_counts.to_dict()
    
    # Yearly distribution
    if 'year' in proposal_df.columns:
        year_counts = proposal_df['year'].value_counts().sort_index()
        insights['yearly_distribution'] = year_counts.to_dict()
    
    # Calculate conversion rate (OK vs Total)
    if 'status' in proposal_df.columns:
        ok_count = len(proposal_df[proposal_df['status'].str.upper() == 'OK'])
        insights['conversion_rate'] = (ok_count / len(proposal_df)) * 100 if len(proposal_df) > 0 else 0
    
    return insights

# ===================== PROPOSAL DASHBOARD (Structured like Payment Dashboard) =====================
def display_proposal_dashboard(proposal_df):
    """Display proposal dashboard structured like payment dashboard"""
    
    if proposal_df.empty:
        st.error("❌ No proposal data available. Please check your connection and try again.")
        st.info("""
        **Troubleshooting steps:**
        1. Check if the Google Sheet is shared with the service account email
        2. Verify the Proposal GID (`1356001164`) is correct
        3. Check if the proposal sheet exists in the spreadsheet
        4. Ensure the service account JSON file is in the correct location
        5. Refresh the page and try again
        """)
        return
    
    # Get insights
    insights = get_proposal_insights(proposal_df)
    
    # ===================== PROPOSAL KPIs =====================
    total_proposals = insights.get('total_proposals', 0)
    total_value = insights.get('total_value', 0)
    
    # Calculate approved/OK count
    approved_count = 0
    if 'status' in proposal_df.columns:
        approved_count = len(proposal_df[proposal_df['status'].str.upper() == 'OK'])
    
    # Calculate Follow-up count (changed from dropped/rejected)
    followup_count = 0
    if 'status' in proposal_df.columns:
        # Count Drop status as Follow-up
        followup_count = len(proposal_df[proposal_df['status'].str.upper() == 'DROP'])
    
    # Calculate conversion rate
    conversion_rate = insights.get('conversion_rate', 0)
    
    st.markdown('<div class="section-header">📊 Proposal Overview</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="kpi-row">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Total Proposals</div>
                <div class="metric-value">{total_proposals}</div>
            </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Total Value</div>
                <div class="metric-value">₹ {total_value:,.2f}</div>
            </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Approved/OK</div>
                <div class="metric-value">{approved_count}</div>
            </div>
        """, unsafe_allow_html=True)
    
    with col4:
        # Changed from "Dropped/Rejected" to "Follow-up"
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Follow-up</div>
                <div class="metric-value">{followup_count}</div>
            </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ===================== PIE CHARTS SECTION =====================
    st.markdown('<div class="section-header">📈 Proposal Analytics</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    # Pie chart: Proposal Status Distribution
    with col1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown("**Proposal Status Distribution**")
        
        if 'status' in proposal_df.columns and not proposal_df['status'].empty:
            status_counts = proposal_df['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            
            # Define color mapping for specific status values
            status_colors = {
                'OK': '#10B981',
                'Drop': '#F59E0B',  # Changed from #EF4444 to #F59E0B for Follow-up
                'Pending': '#F59E0B',
                'Approved': '#10B981',
                'Rejected': '#EF4444',
                'Under Review': '#8B5CF6',
                'Ongoing': '#3B82F6',
                'Others': '#6B7280',
                'Follow-up': '#F59E0B'  # Added Follow-up color
            }
            
            # Create pie chart
            fig = px.pie(status_counts, names='Status', values='Count', hole=0.4,
                        color='Status', color_discrete_map=status_colors)
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color="white",
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=400
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Status data not available in proposal data")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Pie chart: Present Status Distribution
    with col2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown("**Present Status Distribution**")
        
        if 'present_status' in proposal_df.columns and not proposal_df['present_status'].empty:
            present_status_counts = proposal_df['present_status'].value_counts().reset_index()
            present_status_counts.columns = ['Present Status', 'Count']
            
            # Define color mapping
            present_status_colors = {
                'Ongoing': '#3B82F6',
                'Others': '#6B7280',
                'Approved': '#10B981',
                'Pending': '#F59E0B',
                'Completed': '#10B981',
                'Rejected': '#EF4444',
                'Follow-up': '#F59E0B'  # Added Follow-up color
            }
            
            # Create pie chart
            fig2 = px.pie(present_status_counts, names='Present Status', values='Count', hole=0.4,
                         color='Present Status', color_discrete_map=present_status_colors)
            fig2.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color="white",
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=400
            )
            fig2.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Present Status data not available")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # ===================== VALUE ANALYSIS =====================
    col1, col2 = st.columns(2)
    
    # Bar chart: Value by Status
    with col1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown("**Total Value by Status**")
        
        if 'amount' in proposal_df.columns and 'status' in proposal_df.columns:
            value_by_status = proposal_df.groupby('status')['amount'].sum().reset_index()
            value_by_status = value_by_status.sort_values('amount', ascending=False)
            
            fig3 = px.bar(value_by_status, x='status', y='amount',
                         labels={'amount': 'Total Value (₹)', 'status': 'Status'},
                         color='status',
                         color_discrete_map={
                             'OK': '#10B981',
                             'Drop': '#F59E0B',  # Changed from #EF4444 to #F59E0B for Follow-up
                             'Pending': '#F59E0B',
                             'Approved': '#10B981',
                             'Follow-up': '#F59E0B'  # Added Follow-up color
                         })
            fig3.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color="white",
                xaxis_title="Status",
                yaxis_title="Total Value (₹)",
                showlegend=False
            )
            fig3.update_traces(texttemplate='₹%{y:,.2f}', textposition='outside')
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Amount or Status data not available for value analysis")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Horizontal bar chart: Top Clients
    with col2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown("**Top Clients by Proposal Value**")
        
        if 'amount' in proposal_df.columns and 'name' in proposal_df.columns:
            # Extract client names (take first part before comma)
            proposal_df['client_short'] = proposal_df['name'].apply(
                lambda x: str(x).split(',')[0].strip() if pd.notnull(x) else 'Unknown'
            )
            
            top_clients = proposal_df.groupby('client_short')['amount'].sum().reset_index()
            top_clients = top_clients.sort_values('amount', ascending=False).head(10)
            
            fig4 = px.bar(top_clients, x='amount', y='client_short', orientation='h',
                         labels={'amount': 'Total Value (₹)', 'client_short': 'Client'},
                         color='amount',
                         color_continuous_scale='Viridis')
            fig4.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color="white",
                xaxis_title="Total Value (₹)",
                yaxis_title="Client",
                showlegend=False
            )
            fig4.update_traces(texttemplate='₹%{x:,.2f}', textposition='outside')
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("Amount or Name data not available for client analysis")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # ===================== STATUS SUMMARY =====================
    st.markdown('<div class="section-header">📝 Status Summary</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="status-summary">', unsafe_allow_html=True)
        st.markdown("**Proposal Status Breakdown**")
        
        if 'status' in proposal_df.columns:
            status_summary = proposal_df['status'].value_counts().reset_index()
            status_summary.columns = ['Status', 'Count']
            
            for _, row in status_summary.iterrows():
                status = row['Status']
                count = row['Count']
                
                # Determine CSS class based on status
                if status.upper() == 'OK':
                    status_class = "status-ok"
                elif status.upper() == 'DROP':
                    status_class = "status-followup"  # Changed from "status-drop" to "status-followup"
                elif 'pending' in status.lower():
                    status_class = "status-pending"
                elif 'ongoing' in status.lower():
                    status_class = "status-ongoing"
                elif 'follow' in status.lower():
                    status_class = "status-followup"
                else:
                    status_class = "status-others"
                
                st.markdown(f"""
                    <div class="status-item">
                        <span class="{status_class}">{status}</span>
                        <span>{count}</span>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No status data available in proposal data")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="status-summary">', unsafe_allow_html=True)
        st.markdown("**Present Status Breakdown**")
        
        if 'present_status' in proposal_df.columns:
            present_status_summary = proposal_df['present_status'].value_counts().reset_index()
            present_status_summary.columns = ['Present Status', 'Count']
            
            for _, row in present_status_summary.iterrows():
                present_status = row['Present Status']
                count = row['Count']
                
                # Determine CSS class based on present status
                if 'ongoing' in present_status.lower():
                    status_class = "status-ongoing"
                elif 'approved' in present_status.lower():
                    status_class = "status-approved"
                elif 'pending' in present_status.lower():
                    status_class = "status-pending"
                elif 'rejected' in present_status.lower():
                    status_class = "status-rejected"
                elif 'follow' in present_status.lower():
                    status_class = "status-followup"
                else:
                    status_class = "status-others"
                
                st.markdown(f"""
                    <div class="status-item">
                        <span class="{status_class}">{present_status}</span>
                        <span>{count}</span>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No present status data available")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # ===================== DISTRIBUTION CHARTS =====================
    st.markdown('<div class="section-header">📋 Distribution Analysis</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown("**Industry Type Distribution**")
        
        if 'industry_type' in proposal_df.columns and not proposal_df['industry_type'].empty:
            industry_counts = proposal_df['industry_type'].value_counts().reset_index()
            industry_counts.columns = ['Industry Type', 'Count']
            
            fig5 = px.pie(industry_counts, names='Industry Type', values='Count', hole=0.4)
            fig5.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color="white",
                showlegend=True,
                height=400
            )
            fig5.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.info("Industry Type data not available")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown("**Source Distribution**")
        
        if 'source' in proposal_df.columns and not proposal_df['source'].empty:
            source_counts = proposal_df['source'].value_counts().reset_index()
            source_counts.columns = ['Source', 'Count']
            
            fig6 = px.bar(source_counts, x='Source', y='Count',
                         labels={'Count': 'Number of Proposals', 'Source': 'Source'},
                         color='Count',
                         color_continuous_scale='Blues')
            fig6.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color="white",
                xaxis_title="Source",
                yaxis_title="Number of Proposals",
                showlegend=False
            )
            fig6.update_traces(texttemplate='%{y}', textposition='outside')
            st.plotly_chart(fig6, use_container_width=True)
        else:
            st.info("Source data not available")
        st.markdown('</div>', unsafe_allow_html=True)

# ===================== MAIN DATA LOADING LOGIC =====================
def load_data():
    st.sidebar.header("🔧 Data Configuration")
    
    # Display current configuration
    st.sidebar.info(f"""
    **Current Setup:**
    - Spreadsheet: `{SPREADSHEET_ID}`
    - Payment Sheet GID: `{SHEET_GID}`
    - Proposal Sheet GID: `{PROPOSAL_GID}`
    """)
    
    # Data source selection
    data_source = st.sidebar.radio(
        "Select Data Source:",
        ["Service Account (Most Accurate)", "CSV Export", "Demo Data"],
        index=0
    )
    
    df = None
    
    if data_source == "Service Account (Most Accurate)":
        df = load_via_service()
        if df is None:
            st.sidebar.warning("🔄 Service Account failed, trying CSV...")
            df = load_via_csv()
            
    elif data_source == "CSV Export":
        df = load_via_csv()
        if df is None:
            st.sidebar.warning("🔄 CSV failed, trying Service Account...")
            df = load_via_service()
        
    else:  # Demo Data
        df = load_demo_data()
        st.sidebar.info("📋 Using Demo Data for display")
    
    # Final fallback to demo data
    if df is None or df.empty:
        st.error("❌ Could not load data from either source. Using demo data.")
        df = load_demo_data()
        st.warning("⚠️ Displaying DEMO DATA - Check your spreadsheet sharing settings")
    
    return process_raw_data(df)

def load_proposals():
    """Load proposal data from Google Sheets"""
    st.sidebar.subheader("📋 Proposal Data Loading")
    
    # Try to load real proposal data via Service Account
    proposal_df = load_proposal_data()
    
    # If service account fails, try CSV export
    if proposal_df is None or proposal_df.empty:
        st.sidebar.warning("🔄 Service Account failed for proposals, trying CSV export...")
        proposal_df = load_proposal_via_csv()
    
    # If still no data, show error
    if proposal_df is None or proposal_df.empty:
        st.sidebar.error("❌ Failed to load proposal data from Google Sheets")
        st.sidebar.info("""
        **Possible solutions:**
        1. Check if the Google Sheet is shared with the service account
        2. Verify the Proposal GID is correct
        3. Check if the proposal sheet exists
        4. Ensure service account JSON file is correct
        """)
        return pd.DataFrame()  # Return empty dataframe
    
    return process_proposal_data(proposal_df)

# ===================== MAIN APP =====================
def main():
    st.title("💼 Payment & Proposal Dashboard")
    
    # Create tabs for Payment and Proposal data
    tab1, tab2 = st.tabs(["💰 Payment Dashboard", "📋 Proposals Dashboard"])
    
    # 🔄 REFRESH BUTTON
    if st.button("🔄 Refresh All Data", type="primary"):
        st.cache_data.clear()
        st.rerun()
    
    # Load both datasets
    with st.spinner("Loading payment data..."):
        df = load_data()
    
    with st.spinner("Loading proposal data..."):
        proposal_df = load_proposals()
    
    # ===================== PAYMENT DASHBOARD TAB =====================
    with tab1:
        if df.empty:
            st.warning("No payment data loaded. Please check your connection and try again.")
        else:
            # ===================== KPIs =====================
            total_order = df["order_amount"].sum()
            total_final = df["final_amount"].sum()
            total_received = df["payment_received"].sum()
            total_pending = df["pending_amount"].sum()
            
            st.markdown('<div class="section-header">📈 Key Performance Indicators</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="kpi-row">', unsafe_allow_html=True)
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Total Order Amount</div>
                        <div class="metric-value">₹ {total_order:,.2f}</div>
                    </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Total Final Amount</div>
                        <div class="metric-value">₹ {total_final:,.2f}</div>
                    </div>
                """, unsafe_allow_html=True)
            
            with col3:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Total Received</div>
                        <div class="metric-value">₹ {total_received:,.2f}</div>
                    </div>
                """, unsafe_allow_html=True)
            
            with col4:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Total Pending</div>
                        <div class="metric-value">₹ {total_pending:,.2f}</div>
                    </div>
                """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # ===================== PIE CHARTS SECTION =====================
            st.markdown('<div class="section-header">💰 Payment Analytics</div>', unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            
            # Pie chart: Pending vs Received
            with col1:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.markdown("**Pending vs Received**")
                
                pie_df = pd.DataFrame({
                    "Status": ["Received", "Pending"],
                    "Amount": [total_received, total_pending]
                })
                
                colors = ['#10B981', '#EF4444']
                
                fig = px.pie(pie_df, names="Status", values="Amount", hole=0.45,
                            color_discrete_sequence=colors)
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font_color="white",
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    height=400
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Pie chart: Payment mode distribution
            with col2:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.markdown("**Payment Mode Distribution**")
                
                if "payment_mode" in df.columns and not df["payment_mode"].empty:
                    mode_df = df.groupby("payment_mode")["payment_received"].sum().reset_index()
                    mode_df = mode_df[mode_df["payment_received"] > 0]
                    
                    if not mode_df.empty:
                        fig2 = px.pie(mode_df, names="payment_mode", values="payment_received", 
                                    hole=0.45, color_discrete_sequence=px.colors.qualitative.Set3)
                        fig2.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            font_color="white",
                            showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            height=400
                        )
                        fig2.update_traces(textposition='inside', textinfo='percent+label')
                        st.plotly_chart(fig2, use_container_width=True)
                    else:
                        st.info("No payment mode data available")
                else:
                    st.info("Payment Mode column not available")
                st.markdown('</div>', unsafe_allow_html=True)
            
            # ===================== STATUS WISE PENDING PIE CHART =====================
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.markdown("**Status-wise Pending Distribution**")
                
                status_pending = df.groupby("work_status")["pending_amount"].sum().reset_index()
                status_pending = status_pending[status_pending["pending_amount"] > 0]
                
                if not status_pending.empty:
                    fig3 = px.pie(status_pending, names="work_status", values="pending_amount", 
                                hole=0.45, color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig3.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        font_color="white",
                        showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        height=400
                    )
                    fig3.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig3, use_container_width=True)
                else:
                    st.info("No pending amounts by status")
                st.markdown('</div>', unsafe_allow_html=True)
            
            # ===================== STATUS WISE SUMMARY =====================
            with col2:
                st.markdown('<div class="status-summary">', unsafe_allow_html=True)
                st.markdown("**Status-wise Summary**")
                
                summary = df.groupby("work_status").agg(
                    count=("work_status", "count"),
                    actual_pending=("pending_amount", "sum"),
                    total_final=("final_amount", "sum"),
                    total_received=("payment_received", "sum")
                ).reset_index()
                
                for _, row in summary.iterrows():
                    if row["work_status"].lower() == "completed":
                        pending_display = 0.0
                        status_color = "#10B981"
                    else:
                        pending_display = row["actual_pending"]
                        status_color = "#F59E0B"
                    
                    st.markdown(f"""
                        <div class="status-item">
                            <span style="color: {status_color}; font-weight: 600;">{row['work_status']}</span>
                            <span>Count: {row['count']} | ₹ {pending_display:,.2f}</span>
                        </div>
                    """, unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            # ===================== YEARLY SUMMARY CHART =====================
            st.markdown('<div class="section-header">📅 Year-wise Summary</div>', unsafe_allow_html=True)
            
            if 'year' in df.columns:
                yearly_data = df.groupby('year')[
                    ['order_amount', 'final_amount', 'payment_received', 'pending_amount']
                ].sum().reset_index()
                
                if not yearly_data.empty:
                    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                    fig4 = px.bar(
                        yearly_data,
                        x='year',
                        y=['order_amount', 'final_amount', 'payment_received'],
                        title='Year-wise Amount Comparison',
                        labels={'value': 'Amount (₹)', 'year': 'Year', 'variable': 'Type'},
                        barmode='group',
                        color_discrete_sequence=['#3B82F6', '#8B5CF6', '#10B981']
                    )
                    fig4.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        font_color="white",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig4, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
            
            # ===================== FILTERS SECTION =====================
            st.markdown('<div class="section-header">🔍 Filter Records</div>', unsafe_allow_html=True)
            
            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
            
            with filter_col1:
                # Status filter
                status_options = ["All"] + sorted(list(df["work_status"].unique()))
                selected_status = st.selectbox("Filter by Status", status_options, key="payment_status")
            
            with filter_col2:
                # Payment mode filter
                if "payment_mode" in df.columns:
                    mode_options = ["All"] + sorted(list(df["payment_mode"].unique()))
                    selected_mode = st.selectbox("Filter by Payment Mode", mode_options, key="payment_mode_filter")
                else:
                    selected_mode = "All"
            
            with filter_col3:
                # Unit filter
                if "unit_name" in df.columns:
                    unit_options = ["All"] + sorted(list(df["unit_name"].dropna().unique()))
                    selected_unit = st.selectbox("Filter by Unit", unit_options, key="payment_unit")
                else:
                    selected_unit = "All"
            
            with filter_col4:
                # Amount range filter
                min_amount = float(df["final_amount"].min())
                max_amount = float(df["final_amount"].max())
                amount_range = st.slider(
                    "Filter by Final Amount (₹)",
                    min_value=min_amount,
                    max_value=max_amount,
                    value=(min_amount, max_amount),
                    key="payment_amount"
                )
            
            # Apply filters
            filtered_df = df.copy()
            if selected_status != "All":
                filtered_df = filtered_df[filtered_df["work_status"] == selected_status]
            
            if selected_mode != "All" and "payment_mode" in filtered_df.columns:
                filtered_df = filtered_df[filtered_df["payment_mode"] == selected_mode]
            
            if selected_unit != "All" and "unit_name" in filtered_df.columns:
                filtered_df = filtered_df[filtered_df["unit_name"] == selected_unit]
            
            filtered_df = filtered_df[
                (filtered_df["final_amount"] >= amount_range[0]) & 
                (filtered_df["final_amount"] <= amount_range[1])
            ]
            
            # ===================== RECORDS TABLE =====================
            st.markdown('<div class="section-header">📋 Detailed Records</div>', unsafe_allow_html=True)
            
            # Display filtered results summary
            st.metric("Filtered Records", len(filtered_df))
            
            # Data table with better styling
            display_columns = []
            for col in ['unit_name', 'work_order_no', 'order_amount', 'final_amount', 
                        'payment_received', 'pending_amount', 'payment_mode', 'work_status', 'date']:
                if col in filtered_df.columns:
                    display_columns.append(col)
            
            if display_columns:
                # Format numeric columns for display
                display_df = filtered_df[display_columns].copy()
                numeric_cols = ['order_amount', 'final_amount', 'payment_received', 'pending_amount']
                for col in numeric_cols:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].apply(lambda x: f"₹ {x:,.2f}")
                
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    height=400
                )
            else:
                st.dataframe(filtered_df, use_container_width=True, height=400)
            
            # ===================== DOWNLOAD SECTION =====================
            st.markdown("---")
            csv = filtered_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Filtered CSV", 
                csv, 
                "filtered_payment_data.csv",
                type="primary"
            )
    
    # ===================== PROPOSAL DASHBOARD TAB =====================
    with tab2:
        # Display Proposal Dashboard (Structured like Payment Dashboard)
        display_proposal_dashboard(proposal_df)
        
        if not proposal_df.empty:
            # ===================== PROPOSAL FILTERS SECTION =====================
            st.markdown('<div class="section-header">🔍 Filter Proposals</div>', unsafe_allow_html=True)
            
            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
            
            with filter_col1:
                # Status filter for proposals
                if 'status' in proposal_df.columns:
                    proposal_status_options = ["All"] + sorted(list(proposal_df['status'].dropna().unique()))
                    selected_proposal_status = st.selectbox("Filter by Status", proposal_status_options, key="proposal_status")
                else:
                    selected_proposal_status = "All"
            
            with filter_col2:
                # Present Status filter
                if 'present_status' in proposal_df.columns:
                    present_status_options = ["All"] + sorted(list(proposal_df['present_status'].dropna().unique()))
                    selected_present_status = st.selectbox("Filter by Present Status", present_status_options, key="present_status")
                else:
                    selected_present_status = "All"
            
            with filter_col3:
                # Client filter
                if 'name' in proposal_df.columns:
                    client_options = ["All"] + sorted(list(proposal_df['name'].dropna().unique()))
                    selected_client = st.selectbox("Filter by Client", client_options, key="proposal_client")
                else:
                    selected_client = "All"
            
            with filter_col4:
                # Amount range filter for proposals
                if 'amount' in proposal_df.columns:
                    prop_min = float(proposal_df['amount'].min())
                    prop_max = float(proposal_df['amount'].max())
                    prop_range = st.slider(
                        "Filter by Amount (₹)",
                        min_value=prop_min,
                        max_value=prop_max,
                        value=(prop_min, prop_max),
                        key="proposal_amount_range"
                    )
                else:
                    prop_range = (0, 100000000)
            
            # Apply proposal filters
            filtered_proposals = proposal_df.copy()
            
            if selected_proposal_status != "All" and 'status' in filtered_proposals.columns:
                filtered_proposals = filtered_proposals[filtered_proposals['status'] == selected_proposal_status]
            
            if selected_present_status != "All" and 'present_status' in filtered_proposals.columns:
                filtered_proposals = filtered_proposals[filtered_proposals['present_status'] == selected_present_status]
            
            if selected_client != "All" and 'name' in filtered_proposals.columns:
                filtered_proposals = filtered_proposals[filtered_proposals['name'] == selected_client]
            
            if 'amount' in filtered_proposals.columns:
                filtered_proposals = filtered_proposals[
                    (filtered_proposals['amount'] >= prop_range[0]) & 
                    (filtered_proposals['amount'] <= prop_range[1])
                ]
            
            # ===================== PROPOSAL DATA TABLE =====================
            st.markdown('<div class="section-header">📋 Proposal Details</div>', unsafe_allow_html=True)
            
            # Display filtered proposal count
            st.metric("Filtered Proposals", len(filtered_proposals))
            
            # Display proposal table with styling
            if not filtered_proposals.empty:
                # Format the display dataframe
                display_proposal_df = filtered_proposals.copy()
                
                # Format numeric columns
                if 'amount' in display_proposal_df.columns:
                    display_proposal_df['amount'] = display_proposal_df['amount'].apply(
                        lambda x: f"₹ {x:,.2f}" if pd.notnull(x) else "N/A"
                    )
                
                # Format dates
                date_columns = ['date', 'wo_date']
                for date_col in date_columns:
                    if date_col in display_proposal_df.columns:
                        display_proposal_df[date_col] = display_proposal_df[date_col].apply(
                            lambda x: x.strftime('%d-%m-%Y') if pd.notnull(x) else ''
                        )
                
                # Select columns to display
                display_cols = []
                for col in ['s_no', 'sno', 'year', 'date', 'name', 'industry_type', 'district', 
                           'scope_of_work', 'type', 'source', 'status', 'refrence_no', 
                           'contact_person', 'amount', 'present_status']:
                    if col in display_proposal_df.columns:
                        display_cols.append(col)
                
                if display_cols:
                    # Display the dataframe
                    st.dataframe(
                        display_proposal_df[display_cols],
                        use_container_width=True,
                        height=500
                    )
                else:
                    st.dataframe(display_proposal_df, use_container_width=True, height=500)
                
                # Download button for proposals
                st.markdown("---")
                proposal_csv = filtered_proposals.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Download Filtered Proposals CSV", 
                    proposal_csv, 
                    "filtered_proposals_data.csv",
                    type="primary"
                )
            else:
                st.info("No proposals match the selected filters.")
    
    # ===================== FOOTER =====================
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #6B7280; font-size: 0.8rem;'>"
        "Payment & Proposal Dashboard • Built with Streamlit • Data updates automatically"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
