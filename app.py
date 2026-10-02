import streamlit as st
import pandas as pd
import numpy as np
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import json

# --- การเชื่อมต่อ Firebase (รองรับ Streamlit Cloud Secrets) ---
if not firebase_admin._apps:
    if "firebase" in st.secrets:
        # แปลงค่าตระกูล Secrets บน Cloud ให้เป็นดิกชันนารีเพื่อเชื่อมต่อ
        secret_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(secret_dict)
    else:
        # กรณีรันบนเครื่องคอมพิวเตอร์ตัวเอง (Local)
        cred = credentials.Certificate(r"serviceAccount.json")
    
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 3. ฟังก์ชันดึงข้อมูลจาก Firestore (อัปเดต: ดึง Document ID มาด้วย) ---
@st.cache_data(ttl=10)
def load_data():
    docs = db.collection('flood_reports').order_by('timestamp', direction=firestore.Query.DESCENDING).get()
    data = []
    for doc in docs:
        doc_data = doc.to_dict()
        data.append({
            "id": doc.id, # สำคัญมาก! ดึงรหัสเฉพาะของแต่ละเคสมาด้วย
            "ผู้แจ้ง": doc_data.get('name', ''),
            "ปัญหา": doc_data.get('issue', ''),
            "พิกัด/รายละเอียด": doc_data.get('detail', ''),
            "สถานะ": doc_data.get('status', 'รอตรวจสอบ'),
            "lat": float(doc_data.get('lat', 14.0208)),
            "lon": float(doc_data.get('lon', 100.5250))
        })
    return pd.DataFrame(data)

df_reports = load_data()

# --- 4. สรุปตัวเลขสถิติ (Metrics) ---
total_cases = len(df_reports)
pending_cases = len(df_reports[df_reports['สถานะ'] == 'รอตรวจสอบ']) if not df_reports.empty else 0

col1, col2, col3 = st.columns(3)
col1.metric("ระดับน้ำเจ้าพระยา (ม.รทก.)", "2.15", "+0.10 ม.", delta_color="inverse")
col2.metric("ปริมาณฝนสะสม (มม.)", "45.0", "-2.0 มม.", delta_color="normal")
col3.metric("เคสรอความช่วยเหลือ (จุด)", f"{pending_cases}", f"จากทั้งหมด {total_cases} แจ้งเหตุ", delta_color="inverse")

# --- 5. แสดงตารางและแผนที่ ---
st.write("---")
st.subheader("📋 รายงานสถานการณ์ล่าสุดจากพื้นที่")
if not df_reports.empty:
    # ซ่อนคอลัมน์ id, lat, lon เวลาแสดงตาราง
    st.dataframe(df_reports.drop(columns=['id', 'lat', 'lon']), use_container_width=True)
else:
    st.info("ยังไม่มีข้อมูลรายงานสถานการณ์ในขณะนี้")

st.write("---")
st.subheader("📍 แผนที่จุดเสี่ยง (พิกัดจริงจากผู้แจ้ง)")
if not df_reports.empty:
    # เพิ่มการเปลี่ยนสีหมุด: ถ้ารอตรวจสอบเป็นสีแดง, กำลังเข้าช่วยเหลือสีเหลือง, ช่วยเหลือแล้วสีเขียว
    st.map(df_reports[['lat', 'lon']], zoom=11)
else:
    st.info("ยังไม่มีหมุดแจ้งเหตุบนแผนที่")

# --- 6. ฟอร์มรายงานสถานการณ์ ---
st.write("---")
st.subheader("📢 แจ้งเหตุ / ขอความช่วยเหลือ")
st.markdown("**ขั้นตอนที่ 1: ดึงพิกัดตำแหน่งปัจจุบันของคุณ**")
location = streamlit_geolocation() 

current_lat = 14.020800
current_lon = 100.525000

if location and location.get('latitude') is not None:
    current_lat = location['latitude']
    current_lon = location['longitude']
    st.success("✅ ดึงพิกัดสำเร็จ!")
else:
    st.info("ℹ️ หากไม่ดึงพิกัด ระบบจะใช้พิกัดเริ่มต้น (สามารถพิมพ์ตัวเลขแก้เองได้)")

st.markdown("**ขั้นตอนที่ 2: กรอกรายละเอียดและส่งข้อมูล**")
with st.form("real_firebase_form", clear_on_submit=True):
    name = st.text_input("ชื่อผู้แจ้ง")
    issue = st.selectbox("ประเภทเหตุการณ์", ["น้ำท่วมผิวจราจร (รถสัญจรลำบาก)", "น้ำเข้าบ้านเรือน", "ขอรับกระสอบทราย", "แจ้งอพยพผู้ป่วยติดเตียง/กลุ่มเปราะบาง", "อื่นๆ"])
    detail = st.text_area("รายละเอียดเพิ่มเติม (เช่น ชื่อหมู่บ้าน, ซอย, จุดสังเกต)")
    
    col_lat, col_lon = st.columns(2)
    with col_lat:
        input_lat = st.number_input("Latitude", value=float(current_lat), format="%.6f")
    with col_lon:
        input_lon = st.number_input("Longitude", value=float(current_lon), format="%.6f")
        
    submit = st.form_submit_button("ส่งรายงานเหตุการณ์")
    
    if submit:
        if name and detail:
            try:
                db.collection('flood_reports').document().set({
                    'name': name,
                    'issue': issue,
                    'detail': detail,
                    'lat': input_lat, 
                    'lon': input_lon, 
                    'status': 'รอตรวจสอบ',
                    'timestamp': firestore.SERVER_TIMESTAMP
                })
                st.success(f"ส่งข้อมูลสำเร็จ! ขอบคุณคุณ {name}")
                st.cache_data.clear()
                st.rerun() 
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {e}")
        else:
            st.warning("กรุณากรอกชื่อและรายละเอียดให้ครบถ้วน")

# --- 7. ระบบจัดการสำหรับแอดมิน (อัปเดตสถานะ) ---
st.write("---")
with st.expander("🛠️ ส่วนจัดการสำหรับเจ้าหน้าที่ (Admin Panel)"):
    if not df_reports.empty:
        # ดึงรายชื่อเคสทั้งหมดมาทำเป็นตัวเลือกใน Dropdown
        # สร้างฟังก์ชันรูปแบบข้อความให้โชว์ "ชื่อผู้แจ้ง - ปัญหา"
        def format_case(doc_id):
            row = df_reports[df_reports['id'] == doc_id].iloc[0]
            return f"คุณ {row['ผู้แจ้ง']} (ปัญหา: {row['ปัญหา']}) - สถานะปัจจุบัน: {row['สถานะ']}"

        st.markdown("**อัปเดตสถานะการเข้าช่วยเหลือ**")
        
        # 1. เลือกเคสที่จะอัปเดต
        selected_doc_id = st.selectbox("เลือกเคสที่ต้องการจัดการ", df_reports['id'].tolist(), format_func=format_case)
        
        # 2. เลือกสถานะใหม่
        new_status = st.radio("ปรับสถานะเป็น:", ["รอตรวจสอบ", "กำลังเข้าช่วยเหลือ", "ช่วยเหลือเรียบร้อย"], horizontal=True)
        
        # 3. ปุ่มกดอัปเดต
        if st.button("💾 บันทึกสถานะ"):
            try:
                # คำสั่ง .update() คือการไปแก้ไขข้อมูลเดิมใน Firebase
                db.collection('flood_reports').document(selected_doc_id).update({
                    'status': new_status
                })
                st.success("อัปเดตสถานะสำเร็จ!")
                st.cache_data.clear() # ล้างแคชเพื่อให้ตารางโหลดข้อมูลใหม่
                st.rerun() # รีเฟรชหน้าเว็บ
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")
    else:
        st.info("ยังไม่มีเคสให้จัดการครับ")