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
SHEET_NAME = "Pri Payment"
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

# ===================== LOAD VIA SERVICE ACCOUNT =====================
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

# ===================== ENHANCED CSV LOADING =====================
@st.cache_data(ttl=120)
def load_via_csv():
    try:
        # Enhanced CSV URL with multiple format options
        csv_urls = [
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={SHEET_GID}",
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={SHEET_GID}",
        ]
        
        df = None
        last_error = None
        
        for i, csv_url in enumerate(csv_urls):
            try:
                st.sidebar.info(f"🔄 Trying CSV URL {i+1}...")
                
                # Add headers and cache busting
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
                        # Read CSV with flexible settings
                        df = pd.read_csv(
                            io.StringIO(response.text), 
                            encoding=encoding,
                            skip_blank_lines=True,
                            na_filter=False,
                            dtype=str,  # Read all as string first
                            thousands=',',  # Handle comma as thousands separator
                            skipinitialspace=True
                        )
                        
                        # Clean the dataframe
                        df = df.dropna(how='all')  # Remove empty rows
                        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]  # Remove unnamed columns
                        
                        if not df.empty and len(df.columns) > 1:
                            st.sidebar.success(f"✅ CSV loaded: {len(df)} records with encoding {encoding}")
                            return df
                            
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        continue
                        
            except Exception as e:
                last_error = e
                continue
        
        # If all methods failed, try direct pandas read
        try:
            st.sidebar.info("🔄 Trying direct pandas read...")
            df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={SHEET_GID}")
            if not df.empty:
                st.sidebar.success(f"✅ Direct CSV loaded: {len(df)} records")
                return df
        except:
            pass
            
        st.sidebar.error(f"❌ All CSV methods failed")
        return None
        
    except Exception as e:
        st.sidebar.error(f"❌ CSV Export failed: {str(e)}")
        return None

# ===================== DEMO DATA (Fallback) =====================
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
    with st.sidebar.expander("🔍 Debug Info"):
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

# ===================== MAIN DATA LOADING LOGIC =====================
def load_data():
    st.sidebar.header("🔧 Data Configuration")
    
    # Display current configuration
    st.sidebar.info(f"""
    **Current Setup:**
    - Spreadsheet: `{SPREADSHEET_ID}`
    - Sheet GID: `{SHEET_GID}`
    """)
    
    # Data source selection - prioritize Service Account since it works
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

# ===================== MAIN APP =====================
def main():
    st.title("💼 Payment Dashboard")
    
    # 🔄 REFRESH BUTTON
    if st.button("🔄 Refresh Data", type="primary"):
        st.cache_data.clear()
        st.rerun()
    
    # Load data
    df = load_data()
    
    if df.empty:
        st.warning("No data loaded. Please check your connection and try again.")
        st.stop()
    
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
        
        colors = ['#10B981', '#EF4444']  # Green for received, Red for pending
        
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
            mode_df = mode_df[mode_df["payment_received"] > 0]  # Filter out zero values
            
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
                pending_display = 0.0  # Completed should have 0 pending
                status_color = "#10B981"  # Green for completed
            else:
                pending_display = row["actual_pending"]
                status_color = "#F59E0B"  # Amber for pending
            
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
        selected_status = st.selectbox("Filter by Status", status_options)
    
    with filter_col2:
        # Payment mode filter
        if "payment_mode" in df.columns:
            mode_options = ["All"] + sorted(list(df["payment_mode"].unique()))
            selected_mode = st.selectbox("Filter by Payment Mode", mode_options)
        else:
            selected_mode = "All"
    
    with filter_col3:
        # Unit filter
        if "unit_name" in df.columns:
            unit_options = ["All"] + sorted(list(df["unit_name"].dropna().unique()))
            selected_unit = st.selectbox("Filter by Unit", unit_options)
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
            value=(min_amount, max_amount)
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
    
    # ===================== FOOTER =====================
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #6B7280; font-size: 0.8rem;'>"
        "Payment Dashboard • Built with Streamlit • Data updates automatically"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()