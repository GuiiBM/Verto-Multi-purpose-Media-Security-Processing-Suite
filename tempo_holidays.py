# Sistema de feriados para integração no app Tempo
# Este arquivo contém a lógica de feriados que será integrada no TEMPO_HTML

HOLIDAYS_DATA = """
const holidays = {
  fixed: [
    {day: 1, month: 1, name: 'Confraternização Universal', type: 'Nacional'},
    {day: 20, month: 1, name: 'São Sebastião', type: 'Municipal - São Sebastião'},
    {day: 3, month: 2, name: 'Aniversário de Ubatuba', type: 'Municipal - Ubatuba'},
    {day: 14, month: 2, name: 'Dia dos Namorados', type: 'Comemorativa'},
    {day: 8, month: 3, name: 'Dia Internacional da Mulher', type: 'Comemorativa'},
    {day: 21, month: 4, name: 'Tiradentes', type: 'Nacional'},
    {day: 1, month: 5, name: 'Dia do Trabalho', type: 'Nacional'},
    {day: 12, month: 5, name: 'Dia das Mães', type: 'Comemorativa'},
    {day: 13, month: 6, name: 'Dia dos Namorados', type: 'Comemorativa'},
    {day: 24, month: 6, name: 'São João', type: 'Comemorativa'},
    {day: 9, month: 7, name: 'Revolução Constitucionalista', type: 'Estadual - SP'},
    {day: 11, month: 8, name: 'Dia dos Pais', type: 'Comemorativa'},
    {day: 7, month: 9, name: 'Independência do Brasil', type: 'Nacional'},
    {day: 12, month: 10, name: 'Nossa Senhora Aparecida', type: 'Nacional'},
    {day: 31, month: 10, name: 'Halloween', type: 'Comemorativa'},
    {day: 2, month: 11, name: 'Finados', type: 'Nacional'},
    {day: 15, month: 11, name: 'Proclamação da República', type: 'Nacional'},
    {day: 20, month: 11, name: 'Consciência Negra', type: 'Nacional'},
    {day: 25, month: 12, name: 'Natal', type: 'Nacional'},
    {day: 31, month: 12, name: 'Réveillon', type: 'Comemorativa'}
  ],
  movable: function(year) {
    const easter = this.getEaster(year);
    return [
      {date: new Date(easter.getTime() - 47 * 86400000), name: 'Carnaval', type: 'Nacional'},
      {date: new Date(easter.getTime() - 2 * 86400000), name: 'Sexta-feira Santa', type: 'Nacional'},
      {date: easter, name: 'Páscoa', type: 'Comemorativa'},
      {date: new Date(easter.getTime() + 60 * 86400000), name: 'Corpus Christi', type: 'Nacional'}
    ];
  },
  getEaster: function(year) {
    const f = Math.floor, G = year % 19, C = f(year / 100),
          H = (C - f(C / 4) - f((8 * C + 13) / 25) + 19 * G + 15) % 30,
          I = H - f(H / 28) * (1 - f(29 / (H + 1)) * f((21 - G) / 11)),
          J = (year + f(year / 4) + I + 2 - C + f(C / 4)) % 7,
          L = I - J, month = 3 + f((L + 40) / 44),
          day = L + 28 - 31 * f(month / 4);
    return new Date(year, month - 1, day);
  },
  getForMonth: function(month, year) {
    const result = [];
    this.fixed.forEach(h => {
      if (h.month - 1 === month) {
        result.push({day: h.day, name: h.name, type: h.type});
      }
    });
    this.movable(year).forEach(h => {
      if (h.date.getMonth() === month && h.date.getFullYear() === year) {
        result.push({day: h.date.getDate(), name: h.name, type: h.type});
      }
    });
    return result.sort((a, b) => a.day - b.day);
  },
  getForYear: function(year) {
    const result = [];
    this.fixed.forEach(h => {
      result.push({day: h.day, month: h.month, name: h.name, type: h.type});
    });
    this.movable(year).forEach(h => {
      result.push({day: h.date.getDate(), month: h.date.getMonth() + 1, name: h.name, type: h.type});
    });
    return result.sort((a, b) => a.month === b.month ? a.day - b.day : a.month - b.month);
  },
  isHoliday: function(day, month, year) {
    return this.getForMonth(month, year).some(h => h.day === day);
  }
};
"""
