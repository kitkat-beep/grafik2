import pandas as pd
import streamlit as st
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
import logging
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    filename='app.log',
    format='%(asctime)s - %(message)s',
    level=logging.INFO
)

def log_action(action):
    user = st.session_state.get('user', 'unknown')
    logging.info(f"User: {user} - {action}")

# Конфигурация
DAYS_IN_MONTH = 28
NORM_HOURS = 160
WORK_GROUPS = ['ГР1', 'ГР2', 'ГР3', 'ГР4', 'офис']
STATUS_CONFIG = {
    'отпуск': {'color': '#90EE90', 'name': 'Отпуск'},
    'б/л': {'color': '#FFB6C1', 'name': 'Больничный'},
    'уч.отпуск': {'color': '#87CEEB', 'name': 'Учебный отпуск'},
    'переработка': {'color': '#FFFACD', 'name': 'Переработка'}
}

class EmployeeSchedule:
    def __init__(self, name, group, schedule_type, exceptions=None, absences=None):
        self.name = name
        self.group = group
        self.schedule_type = schedule_type
        self.exceptions = exceptions or {}
        self.absences = absences or {}

    def generate_schedule(self):
        base_pattern = SCHEDULE_TEMPLATES[self.schedule_type]
        schedule = {}
        
        pattern_index = 0
        for day in range(1, DAYS_IN_MONTH+1):
            day_str = str(day)
            if day_str in self.exceptions:
                schedule[day_str] = self.exceptions[day_str]
            elif day_str in self.absences:
                schedule[day_str] = self.absences[day_str]
            else:
                schedule[day_str] = base_pattern[pattern_index % len(base_pattern)]
                pattern_index += 1
        
        total = self.calculate_total(schedule)
        
        return {
            'Ф.И.О. мастера смены': self.name,
            'ГР №': self.group,
            **schedule,
            'Факт ФРВ': round(total, 1),
            'от ФРВ': round(total - NORM_HOURS, 1),
            'Статус': self.get_status()
        }

    def calculate_total(self, schedule):
        return sum(
            float(h) if isinstance(h, (int, float, str)) and str(h).replace('.', '').isdigit() 
            else 0 
            for h in schedule.values()
        )

    def get_status(self):
        statuses = set()
        for day in range(1, DAYS_IN_MONTH+1):
            val = self.absences.get(str(day), '')
            if val in STATUS_CONFIG:
                statuses.add(STATUS_CONFIG[val]['name'])
        return ', '.join(statuses) if statuses else 'Активен'

def create_schedule():
    employees = [
        EmployeeSchedule("Феоктистова Е.А.", "ГР1", "График1", {'12': "ГО", '27': '4'}),
        # ... (полный список сотрудников из предыдущего кода)
    ]
    return pd.DataFrame([e.generate_schedule() for e in employees])

def get_column_config():
    column_config = {
        "Ф.И.О. мастера смены": st.column_config.TextColumn(
            "Сотрудник", required=True
        ),
        "ГР №": st.column_config.SelectboxColumn(
            "Группа", options=WORK_GROUPS
        )
    }
    
    for day in range(1, DAYS_IN_MONTH+1):
        column_config[str(day)] = st.column_config.TextColumn(
            str(day),
            help="Часы работы или код статуса",
            validate=lambda x: x in STATUS_CONFIG or x.replace('.', '').isdigit()
        )
    
    return column_config

def apply_absence_template():
    try:
        if 'schedule_data' not in st.session_state:
            st.error("Данные не загружены!")
            return

        employees = st.session_state.schedule_data['Ф.И.О. мастера смены'].tolist()
        templates = {
            "Отпуск": {'code': 'отпуск', 'days': 14},
            "Больничный": {'code': 'б/л', 'days': 7},
            "Учебный отпуск": {'code': 'уч.отпуск', 'days': 5}
        }

        with st.sidebar.expander("📅 Шаблоны отсутствий"):
            template = st.selectbox("Выберите шаблон", list(templates.keys()))
            start_day = st.number_input("Начальный день", 1, DAYS_IN_MONTH, key='template_day')
            selected_employees = st.multiselect("Сотрудники", employees)

            if st.button("Применить"):
                apply_template_to_schedule(
                    templates[template]['code'],
                    templates[template]['days'],
                    start_day,
                    selected_employees
                )
                st.success("Шаблон применен успешно!")

    except Exception as e:
        log_action(f"Ошибка в шаблоне: {str(e)}")
        st.error("Ошибка применения шаблона")

def apply_template_to_schedule(code, days, start_day, employees):
    for emp in employees:
        idx = st.session_state.schedule_data[
            st.session_state.schedule_data['Ф.И.О. мастера смены'] == emp].index[0]
        for i in range(days):
            day = str(start_day + i)
            if int(day) <= DAYS_IN_MONTH:
                st.session_state.schedule_data.at[idx, day] = code

def smart_search(df):
    try:
        search_term = st.sidebar.text_input("🔍 Умный поиск (имя/группа/статус)")
        if search_term:
            return df[
                df.apply(lambda row: any(
                    str(search_term).lower() in str(row[col]).lower()
                    for col in ['Ф.И.О. мастера смены', 'ГР №', 'Статус']
                ), axis=1)
            ]
        return df
    except:
        return df

def show_analytics(df):
    try:
        st.header("📊 Аналитика")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            analysis_type = st.selectbox(
                "Тип анализа", 
                ["Часы работы", "Переработки", "Статусы"]
            )
            date_range = st.slider(
                "Диапазон дней", 
                1, DAYS_IN_MONTH, 
                (1, DAYS_IN_MONTH)
            )

        with col2:
            if analysis_type == "Часы работы":
                fig = px.bar(df, x='Ф.И.О. мастера смены', y='Факт ФРВ',
                            color='ГР №', barmode='group')
            elif analysis_type == "Переработки":
                fig = px.scatter(df, x='Ф.И.О. мастера смены', y='от ФРВ',
                                size='от ФРВ', color='ГР №')
            else:
                status_counts = df['Статус'].value_counts()
                fig = px.pie(status_counts, 
                            values=status_counts.values,
                            names=status_counts.index)
            
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Тепловая карта загруженности")
        heatmap_data = df[[str(d) for d in range(date_range[0], date_range[1]+1)]]
        fig = go.Figure(data=go.Heatmap(
            z=heatmap_data.replace(STATUS_CONFIG.keys(), 0).astype(float).values,
            x=heatmap_data.columns,
            y=df['Ф.И.О. мастера смены'],
            colorscale='Viridis'
        ))
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        log_action(f"Ошибка аналитики: {str(e)}")
        st.error("Ошибка построения аналитики")

def main():
    st.set_page_config(
        page_title="График работы цеха",
        page_icon="📅",
        layout="wide"
    )

    # Инициализация данных
    if 'schedule_data' not in st.session_state:
        st.session_state.schedule_data = create_schedule()

    # Боковая панель
    st.sidebar.header("Управление")
    apply_absence_template()
    
    # Фильтрация и поиск
    filtered_df = smart_search(st.session_state.schedule_data)

    # Основной интерфейс
    st.title("📅 Управление графиком работы цеха")
    
    try:
        # Редактирование данных
        st.header("Табель учета рабочего времени")
        edited_df = st.data_editor(
            filtered_df,
            column_config=get_column_config(),
            num_rows="fixed",
            use_container_width=True,
            key="data_editor"
        )
        
        # Аналитика
        show_analytics(edited_df)

        # Экспорт
        st.sidebar.header("Экспорт")
        if st.sidebar.button("Сохранить данные"):
            export_data(edited_df)

    except Exception as e:
        log_action(f"Критическая ошибка: {str(e)}")
        st.error("Системная ошибка! Перезагрузите приложение")

def export_data(df):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        st.sidebar.download_button(
            label="📥 Скачать Excel",
            data=output.getvalue(),
            file_name=f"график_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        log_action("Экспорт данных")
    except:
        st.error("Ошибка экспорта данных")

if __name__ == "__main__":
    main()