// =============================================================================
// 🚀 AI MOVIE SHORTS - APPS SCRIPT AUTO-LOADER (TỰ ĐỘNG CẬP NHẬT CODE QUA GIST)
// =============================================================================
// Đoạn mã này chỉ cần dán 1 LẦN DUY NHẤT vào Google Apps Script và bấm Deploy.
// Mỗi khi có cập nhật, AI sẽ tự động đẩy code lên Gist và Apps Script tự nạp phiên bản mới nhất!

const GIST_RAW_URL = "https://gist.githubusercontent.com/hoangnamtaichua-prog/021f87edae23873bdedc56cca5984115/raw/ams_license_engine.js";

function getRemoteEngineCode() {
  const url = GIST_RAW_URL + "?v=" + new Date().getTime();
  const response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { "Cache-Control": "no-cache" }
  });
  return response.getContentText();
}

function executeRemoteEngine(fnName, e) {
  const code = getRemoteEngineCode();
  eval(code);
  
  if (fnName === 'doGet') {
    if (typeof handleDoGet === 'function') return handleDoGet(e);
    if (typeof doGet === 'function') return doGet(e);
  }
  if (fnName === 'doPost') {
    if (typeof handleDoPost === 'function') return handleDoPost(e);
    if (typeof doPost === 'function') return doPost(e);
  }
  
  throw new Error("Không tìm thấy hàm " + fnName + " trong Remote Engine!");
}

function doGet(e) {
  try {
    return executeRemoteEngine('doGet', e);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doPost(e) {
  try {
    return executeRemoteEngine('doPost', e);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// Hàm khai báo phạm vi quyền hạn cho Google Apps Script (Chạy 1 lần khi cấp quyền)
function testAuth() {
  SpreadsheetApp.getActiveSpreadsheet();
  UrlFetchApp.fetch("https://www.google.com");
  DriveApp.getRootFolder();
}

