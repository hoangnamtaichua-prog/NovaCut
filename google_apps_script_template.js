/**
 * ==============================================================================
 * GOOGLE APPS SCRIPT WEB APP - HỆ THỐNG QUẢN LÝ BẢN QUYỀN, SEPAY & LƯU KEYS 1 CHIỀU
 * ==============================================================================
 * 
 * 🛡️ NGUYÊN TẮC BẢO MẬT & CHỐNG HACK NGƯỢC (ZERO-KNOWLEDGE READ):
 * 1. Khóa bảo mật API_SECRET_TOKEN: Chỉ ứng dụng chính chủ mới được phép gửi/nhận dữ liệu.
 * 2. Đẩy dữ liệu 1 CHIỀU (WRITE-ONLY): Khi người dùng nhập API GPT hoặc OpenSpeaker, 
 *    app sẽ đẩy 1 chiều lên Google Sheet để bạn quản lý.
 * 3. TUYỆT ĐỐI KHÔNG TRẢ VỀ API KEY: Mọi yêu cầu kiểm tra bản quyền (doGet) chỉ trả về 
 *    trạng thái bản quyền (Hạn dùng, Gói cước), TUYỆT ĐỐI KHÔNG BAO GIỜ TRẢ VỀ API KEY 
 *    để chống kẻ gian hack ngược xem trộm database trong Sheet.
 * ==============================================================================
 * 
 * 📋 CẤU TRÚC BẢNG GOOGLE SHEET (Sheet1 - Dòng 1):
 * [A] HWID
 * [B] Tên Khách Hàng
 * [C] SĐT / Zalo
 * [D] Gói Cước (trial / pro / vip / yearly)
 * [E] Ngày Hết Hạn
 * [F] Trạng Thái (ACTIVE / EXPIRED / BLOCKED)
 * [G] Số Tiền Đã Trả
 * [H] Mã Giao Dịch
 * [I] Ghi Chú
 * [J] OpenAI API Key (Đẩy 1 chiều)
 * [K] OpenAI Base URL
 * [L] OpenAI Model
 * [M] OpenSpeaker API Key (Đẩy 1 chiều)
 * [N] Cập Nhật Lúc
 * ==============================================================================
 */

// 🔑 Khóa bí mật đồng bộ (Phải khớp với api_secret_token trong license_config.json)
const API_SECRET_TOKEN = "AMS_SECURE_TOKEN_2026_@DEEPMIND_ANTIGRAVITY";

// Bảng giá gói cước tương ứng số ngày cộng thêm
const PACKAGE_PRICES = {
  300000: { tier: 'pro', name: 'Gói Pro', days: 30 },
  500000: { tier: 'vip', name: 'Gói VIP', days: 30 },
  3990000: { tier: 'yearly', name: 'Gói 1 Năm', days: 365 }
};

function getLicenseSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName('License') || ss.getSheetByName('Trang tính1') || ss.getSheetByName('Sheet1') || ss.getSheets()[0];
}

function getVersionSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName('Versions') || ss.getSheetByName('Version') || 
         ss.getSheetByName('versions') || ss.getSheetByName('version') ||
         ss.getSheetByName('Phiên bản') || ss.getSheetByName('phien_ban') ||
         (ss.getSheets().length > 1 ? ss.getSheets()[1] : null);
}

function isVersionNewer(latest, current) {
  if (!latest || !current) return false;
  const lParts = String(latest).split('.').map(n => parseInt(n, 10) || 0);
  const cParts = String(current).split('.').map(n => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(lParts.length, cParts.length); i++) {
    const l = lParts[i] || 0;
    const c = cParts[i] || 0;
    if (l > c) return true;
    if (l < c) return false;
  }
  return false;
}

function parseDateValue(val) {
  if (val === null || val === undefined || val === '') return null;
  
  if (val instanceof Date) {
    if (!isNaN(val.getTime())) return val;
  }
  
  // Nếu là số Serial Date của Excel/Google Sheets
  if (typeof val === 'number') {
    const d = new Date(Math.round((val - 25569) * 86400 * 1000));
    if (!isNaN(d.getTime())) return d;
  }

  const str = String(val).trim();
  if (!str) return null;

  // 1. Thử parse định dạng Việt Nam: dd/MM/yyyy hoặc dd/MM/yyyy HH:mm[:ss]
  const vnMatch = str.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (vnMatch) {
    const day = parseInt(vnMatch[1], 10);
    const month = parseInt(vnMatch[2], 10) - 1;
    const year = parseInt(vnMatch[3], 10);
    const hour = parseInt(vnMatch[4] || 0, 10);
    const min = parseInt(vnMatch[5] || 0, 10);
    const sec = parseInt(vnMatch[6] || 0, 10);
    const d = new Date(year, month, day, hour, min, sec);
    if (!isNaN(d.getTime())) return d;
  }

  // 2. Thử parse định dạng YYYY-MM-DD
  const isoMatch = str.match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (isoMatch) {
    const year = parseInt(isoMatch[1], 10);
    const month = parseInt(isoMatch[2], 10) - 1;
    const day = parseInt(isoMatch[3], 10);
    const hour = parseInt(isoMatch[4] || 0, 10);
    const min = parseInt(isoMatch[5] || 0, 10);
    const sec = parseInt(isoMatch[6] || 0, 10);
    const d = new Date(year, month, day, hour, min, sec);
    if (!isNaN(d.getTime())) return d;
  }

  // 3. Thử parse chuẩn JS
  const d3 = new Date(str);
  if (!isNaN(d3.getTime())) return d3;

  return null;
}

function getUpdateInfo(currentVer = '1.0.0') {
  try {
    const verSheet = getVersionSheet();
    if (!verSheet) return { has_update: false, latest_version: currentVer, changelog: '', download_url: '' };
    const verData = verSheet.getDataRange().getValues();
    if (verData.length < 2) return { has_update: false, latest_version: currentVer, changelog: '', download_url: '' };

    // Duyệt qua tất cả các dòng từ dòng 2 trở đi để tìm phiên bản cao nhất
    let bestRow = null;
    let highestVer = '0.0.0';

    for (let i = 1; i < verData.length; i++) {
      const v = String(verData[i][0] || '').trim();
      const fileId = String(verData[i][1] || '').trim();
      if (!v) continue;
      if (isVersionNewer(v, highestVer) || (!bestRow && fileId)) {
        highestVer = v;
        bestRow = verData[i];
      }
    }

    if (!bestRow) bestRow = verData[verData.length - 1];

    const latestVer = String(bestRow[0] || '1.0.0').trim();
    const driveFileId = String(bestRow[1] || '').trim();
    const changelog = String(bestRow[2] || '').trim();
    const isMandatory = Boolean(bestRow[4] === true || String(bestRow[4]).toUpperCase() === 'TRUE' || bestRow[3] === true || String(bestRow[3]).toUpperCase() === 'TRUE');
    const hasUpdate = isVersionNewer(latestVer, currentVer) && Boolean(driveFileId);

    return {
      has_update: hasUpdate,
      current_version: currentVer,
      latest_version: latestVer,
      google_drive_file_id: driveFileId,
      download_url: driveFileId ? `https://drive.google.com/uc?export=download&id=${driveFileId}` : '',
      changelog: changelog,
      is_mandatory: isMandatory
    };
  } catch (e) {
    return { has_update: false, latest_version: currentVer, error: e.toString() };
  }
}

// -----------------------------------------------------------------------------
// 1. XỬ LÝ GET: Kiểm tra bản quyền & Tự động kiểm tra bản cập nhật mới
// -----------------------------------------------------------------------------
function doGet(e) {
  try {
    const params = e.parameter || {};
    const action = params.action;
    const hwid = (params.hwid || '').trim().toUpperCase();
    const token = params.token || '';

    // Xác thực token bí mật
    if (token !== API_SECRET_TOKEN) {
      return jsonResponse({ valid: false, error: 'Unauthorized: Invalid Security Token' });
    }

    // A. KIỂM TRA BẢN CẬP NHẬT MỚI (AUTO-UPDATE)
    if (action === 'check_update') {
      const currentVer = String(params.current_version || '1.0.0').trim();
      const updateInfo = getUpdateInfo(currentVer);
      return jsonResponse(updateInfo);
    }

    // B. KIỂM TRA BẢN QUYỀN HWID
    if (action === 'check_license') {
      if (!hwid) {
        return jsonResponse({ valid: false, error: 'Thiếu HWID' });
      }

      const currentVer = String(params.current_version || '1.0.0').trim();
      const updateInfo = getUpdateInfo(currentVer);

      const sheet = getLicenseSheet();
      const data = sheet.getDataRange().getValues();
      
      // Tìm dòng theo HWID (Cột A)
      for (let i = 1; i < data.length; i++) {
        const rowHwid = String(data[i][0] || '').trim().toUpperCase();
        const cleanRowHwid = rowHwid.replace(/-/g, '').replace(/^AMS/g, '');
        const cleanHwid = hwid.replace(/-/g, '').replace(/^AMS/g, '');
        const isMatch = (rowHwid === hwid) || (cleanRowHwid === cleanHwid) || 
                        (cleanHwid.startsWith(cleanRowHwid) && cleanRowHwid.length >= 6) ||
                        (cleanRowHwid.startsWith(cleanHwid) && cleanHwid.length >= 6);
        if (isMatch) {
          const userName = data[i][1];
          const phoneZalo = data[i][2];
          const tier = String(data[i][3] || 'pro').toLowerCase();
          const expireDateVal = data[i][4];
          const status = String(data[i][5] || 'ACTIVE').toUpperCase();

          const expireDate = parseDateValue(expireDateVal);
          const now = new Date();
          const isValid = status === 'ACTIVE' && expireDate && expireDate.getTime() > now.getTime();
          const expireEpoch = expireDate ? Math.floor(expireDate.getTime() / 1000) : 0;
          const expireStr = expireDate ? Utilities.formatDate(expireDate, "GMT+7", "dd/MM/yyyy HH:mm") : String(expireDateVal || '');

          // 🛡️ ANTI-MITM: Ký số HMAC-SHA256 + Nonce
          const nonce = String(params.nonce || '');
          const serverTime = Math.floor(now.getTime() / 1000);
          const rawSignStr = `${hwid}|${tier}|${status}|${expireStr}|${expireEpoch}|${nonce}|${serverTime}`;
          const sig = computeHmacSha256(rawSignStr, API_SECRET_TOKEN);

          // ⭐ CẤP API KEYS TỰ ĐỘNG CHO NGƯỜI DÙNG
          let vipApiKeys = {};
          if (isValid) {
            // 1. Đọc keys riêng cấu hình theo dòng HWID ở Cột G (Cột 7) hoặc Cột J (Cột 10)
            const colGVal = String(data[i][6] || '').trim();
            const colJVal = String(data[i][9] || '').trim();
            const customKeyVal = colGVal || colJVal;

            if (customKeyVal) {
              if (customKeyVal.startsWith('{') && customKeyVal.endsWith('}')) {
                try { vipApiKeys = JSON.parse(customKeyVal); } catch (e) {}
              } else if (customKeyVal.startsWith('sk-') || customKeyVal.length > 15) {
                vipApiKeys.openaiKey = customKeyVal;
              }
            }

            // Đọc thêm Cột OpenSpeaker (Cột M / Cột 13) nếu có
            const colMVal = String(data[i][12] || '').trim();
            if (colMVal && !vipApiKeys.openSpeakerApiKey) {
              vipApiKeys.openSpeakerApiKey = colMVal;
            }

            // 2. Đọc cấu hình mặc định trong sheet 'Config' (hoặc 'Cấu hình') nếu còn thiếu
            try {
              const cfgSheet = ss.getSheetByName('Config') || ss.getSheetByName('Cấu hình') || ss.getSheetByName('config');
              if (cfgSheet) {
                const cfgRows = cfgSheet.getDataRange().getValues();
                for (let r = 0; r < cfgRows.length; r++) {
                  const k = String(cfgRows[r][0] || '').trim().toUpperCase();
                  const v = String(cfgRows[r][1] || '').trim();
                  if (!v) continue;
                  if (k === 'VIP_OPENAI_KEY' || k === 'OPENAI_KEY' || k === 'OPENAI_API_KEY') {
                    if (!vipApiKeys.openaiKey && !vipApiKeys.openai_key) vipApiKeys.openaiKey = v;
                  } else if (k === 'VIP_GEMINI_KEY' || k === 'GEMINI_KEY' || k === 'GEMINI_API_KEY') {
                    if (!vipApiKeys.geminiKey && !vipApiKeys.gemini_key) vipApiKeys.geminiKey = v;
                  } else if (k === 'VIP_OPENSPEAKER_KEY' || k === 'OPENSPEAKER_KEY' || k === 'OPENSPEAKER_API_KEY') {
                    if (!vipApiKeys.openSpeakerApiKey && !vipApiKeys.api_key) vipApiKeys.openSpeakerApiKey = v;
                  } else if (k === 'VIP_DEEPSEEK_KEY' || k === 'DEEPSEEK_KEY') {
                    if (!vipApiKeys.deepseekKey) vipApiKeys.deepseekKey = v;
                  }
                }
              }
            } catch (cfgErr) {}
          }

          const hasKeys = Object.keys(vipApiKeys).length > 0;

          return jsonResponse({
            valid: isValid,
            hwid: hwid,
            tier: tier,
            user_name: userName,
            phone_zalo: phoneZalo,
            status: status,
            expire_date: expireStr,
            expire_epoch: expireEpoch,
            nonce: nonce,
            server_time: serverTime,
            sig: sig,
            api_keys: (isValid && hasKeys) ? vipApiKeys : null,
            update: updateInfo
          });
        }
      }

      const nonce = String(params.nonce || '');
      const serverTime = Math.floor(new Date().getTime() / 1000);
      const notFoundSignStr = `${hwid}||NOT_FOUND||0|${nonce}|${serverTime}`;
      const notFoundSig = computeHmacSha256(notFoundSignStr, API_SECRET_TOKEN);

      return jsonResponse({ 
        valid: false, 
        hwid: hwid,
        status: 'NOT_FOUND', 
        message: 'Chưa có bản quyền',
        nonce: nonce,
        server_time: serverTime,
        sig: notFoundSig,
        update: updateInfo
      });
    }

    return jsonResponse({ status: 'OK', message: 'License Server is Active & Protected' });
  } catch (err) {
    return jsonResponse({ error: err.toString() });
  }
}

// -----------------------------------------------------------------------------
// 2. XỬ LÝ POST: Webhook SePay, Đăng ký dùng thử & ĐẨY KEYS 1 CHIỀU LÊN SHEET
// -----------------------------------------------------------------------------
function doPost(e) {
  try {
    let body = {};
    if (e.postData && e.postData.contents) {
      try {
        body = JSON.parse(e.postData.contents);
      } catch (ex) {
        body = e.parameter || {};
      }
    }

    const sheet = getLicenseSheet();
    const action = body.action;

    // A. Xử lý Webhook tự động từ SePay khi có chuyển khoản
    if (body.gateway || body.transferAmount || body.content) {
      return handleSePayWebhook(body, sheet);
    }

    // Xác thực token bảo mật cho các hành động từ App
    const token = body.token || '';
    if (token !== API_SECRET_TOKEN) {
      return jsonResponse({ success: false, error: 'Unauthorized: Invalid Security Token' });
    }

    // B. ĐẨY API KEYS 1 CHIỀU LÊN GOOGLE SHEET (WRITE-ONLY)
    if (action === 'sync_keys') {
      const hwid = (body.hwid || '').trim().toUpperCase();
      const shortHwid = (body.short_hwid || '').trim().toUpperCase();
      const openaiKey = body.openai_key || '';
      const openaiBaseUrl = body.openai_base_url || 'https://api.openai.com/v1';
      const openaiModel = body.openai_model || 'gpt-5.6-luna';
      const openSpeakerKey = body.openspeaker_key || '';
      const now = new Date();
      const timeStr = Utilities.formatDate(now, "GMT+7", "dd/MM/yyyy HH:mm");

      if (!hwid && !shortHwid) {
        return jsonResponse({ success: false, error: 'Thiếu HWID' });
      }

      const data = sheet.getDataRange().getValues();
      let rowIndex = -1;

      const cleanHwid = hwid.replace(/-/g, '').replace(/^AMS/g, '');
      const cleanShort = shortHwid.replace(/-/g, '').replace(/^AMS/g, '');

      for (let i = 1; i < data.length; i++) {
        const rowHwid = String(data[i][0] || '').trim().toUpperCase();
        const cleanRowHwid = rowHwid.replace(/-/g, '').replace(/^AMS/g, '');
        if (
          rowHwid === hwid || 
          cleanRowHwid === cleanHwid || 
          (cleanShort && cleanRowHwid === cleanShort) ||
          (cleanHwid && cleanRowHwid && cleanHwid.startsWith(cleanRowHwid) && cleanRowHwid.length >= 4) ||
          (cleanRowHwid && cleanHwid && cleanRowHwid.startsWith(cleanHwid) && cleanHwid.length >= 4)
        ) {
          rowIndex = i + 1; // 1-based index
          break;
        }
      }

      if (rowIndex > 0) {
        // Cập nhật vào dòng của user: Cột J(10), K(11), L(12), M(13), N(14)
        if (openaiKey) sheet.getRange(rowIndex, 10).setValue(openaiKey);
        if (openaiBaseUrl) sheet.getRange(rowIndex, 11).setValue(openaiBaseUrl);
        if (openaiModel) sheet.getRange(rowIndex, 12).setValue(openaiModel);
        if (openSpeakerKey) sheet.getRange(rowIndex, 13).setValue(openSpeakerKey);
        sheet.getRange(rowIndex, 14).setValue(timeStr);
      } else {
        // Nếu user chưa có dòng nào, tạo mới
        sheet.appendRow([
          hwid, 'Khách Tự Nhập Keys', '', 'pro', '', 'ACTIVE', 0, '', 'Tự lưu Keys từ App',
          openaiKey, openaiBaseUrl, openaiModel, openSpeakerKey, timeStr
        ]);
      }

      return jsonResponse({ success: true, message: 'Đã lưu API Keys 1 chiều lên Google Sheet an toàn!' });
    }

    // C. Đăng ký dùng thử Trial 24h
    if (action === 'register_trial') {
      const hwid = (body.hwid || '').trim().toUpperCase();
      const userName = body.user_name || 'Khách Dùng Thử';
      const phoneZalo = body.phone_zalo || '';
      
      const now = new Date();
      const expireDate = new Date(now.getTime() + 24 * 60 * 60 * 1000);
      const expireStr = Utilities.formatDate(expireDate, "GMT+7", "dd/MM/yyyy HH:mm");

      sheet.appendRow([
        hwid, userName, phoneZalo, 'trial', expireDate, 'ACTIVE', 0, 'TRIAL_AUTO', 'Đăng ký dùng thử 24h'
      ]);

      return jsonResponse({ success: true, message: 'Đăng ký dùng thử 24h thành công', expire_date: expireStr });
    }

    // D. TỰ ĐỘNG ĐẨY FILE PATCH LÊN GOOGLE DRIVE & CẬP NHẬT TAB VERSIONS TRÊN GOOGLE SHEET
    if (action === 'publish_patch') {
      const version = String(body.version || '').trim();
      const changelog = String(body.changelog || 'Bản cập nhật tối ưu hóa hiệu năng và sửa lỗi.').trim();
      const isMandatory = Boolean(body.is_mandatory === true);
      const fileBase64 = body.file_base64 || '';
      const fileName = body.file_name || `NovaCut_Patch_v${version}.zip`;

      if (!version || !fileBase64) {
        return jsonResponse({ success: false, error: 'Thiếu version hoặc file_base64' });
      }

      // 1. Tìm hoặc tạo thư mục 'NovaCut_Updates' trên Google Drive
      let folder;
      const folders = DriveApp.getFoldersByName('NovaCut_Updates');
      if (folders.hasNext()) {
        folder = folders.next();
      } else {
        folder = DriveApp.createFolder('NovaCut_Updates');
      }

      // 2. Tạo file zip trên Google Drive từ base64
      const decodedBytes = Utilities.base64Decode(fileBase64);
      const blob = Utilities.newBlob(decodedBytes, 'application/zip', fileName);
      const driveFile = folder.createFile(blob);
      
      // 3. Phân quyền Public ai có link cũng tải được
      driveFile.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      const fileId = driveFile.getId();

      // 4. Ghi nhận vào Tab 'Versions' trên Google Sheet
      const verSheet = getVersionSheet();
      if (verSheet) {
        // Đảm bảo có dòng header
        if (verSheet.getLastRow() === 0) {
          verSheet.appendRow(['Latest_Version', 'Google_Drive_File_ID', 'Changelog', 'Is_Mandatory', 'Updated_At']);
        }
        // Cập nhật dòng 2 (dòng phiên bản phát hành mới nhất)
        verSheet.getRange(2, 1).setValue(version);
        verSheet.getRange(2, 2).setValue(fileId);
        verSheet.getRange(2, 3).setValue(changelog);
        verSheet.getRange(2, 4).setValue(isMandatory ? 'TRUE' : 'FALSE');
        verSheet.getRange(2, 5).setValue(Utilities.formatDate(new Date(), "GMT+7", "dd/MM/yyyy HH:mm:ss"));
      }

      return jsonResponse({
        success: true,
        message: `Đã tự động đẩy bản vá v${version} lên Google Drive & cập nhật Sheet thành công 100%!`,
        version: version,
        google_drive_file_id: fileId,
        download_url: `https://drive.google.com/uc?export=download&id=${fileId}`
      });
    }

    return jsonResponse({ error: 'Hành động không hợp lệ' });
  } catch (err) {
    return jsonResponse({ error: err.toString() });
  }
}

// -----------------------------------------------------------------------------
// 3. XỬ LÝ WEBHOOK SEPAY (VIETQR THANH TOÁN TỰ ĐỘNG)
// -----------------------------------------------------------------------------
function handleSePayWebhook(payload, sheet) {
  const content = String(payload.content || '').toUpperCase();
  const transferAmount = Number(payload.transferAmount || 0);
  const transactionId = String(payload.id || payload.referenceCode || Date.now());

  // Cú pháp nội dung chuyển khoản: AMS <SHORT_HWID> <TIER> (Ví dụ: "AMS A1B2C3 VIP")
  const match = content.match(/AMS\s+([A-Z0-9]{4,12})\s*([A-Z]*)/i);
  if (!match) {
    return jsonResponse({ success: false, message: 'Nội dung chuyển khoản không khớp cú pháp AMS' });
  }

  const shortHwid = match[1].trim().toUpperCase();
  let requestedTier = match[2] ? match[2].trim().toLowerCase() : 'vip';
  if (!requestedTier) requestedTier = 'vip';

  // Xác định gói và số ngày theo số tiền
  let daysToAdd = 30;
  let finalTier = requestedTier;

  if (transferAmount >= 3990000) {
    finalTier = 'yearly';
    daysToAdd = 365;
  } else if (transferAmount >= 500000) {
    finalTier = 'vip';
    daysToAdd = 30;
  } else if (transferAmount >= 300000) {
    finalTier = 'pro';
    daysToAdd = 30;
  }

  const data = sheet.getDataRange().getValues();
  let rowIndex = -1;

  for (let i = 1; i < data.length; i++) {
    const rowHwid = String(data[i][0] || '').replace(/AMS-/g, '').replace(/-/g, '').trim().toUpperCase();
    if (rowHwid.startsWith(shortHwid) || shortHwid.startsWith(rowHwid)) {
      rowIndex = i + 1; // 1-indexed
      break;
    }
  }

  const now = new Date();
  let newExpire = new Date(now.getTime() + daysToAdd * 24 * 60 * 60 * 1000);

  if (rowIndex > 0) {
    // Đã có trong Sheet -> Gia hạn
    const currentExpireVal = sheet.getRange(rowIndex, 5).getValue();
    const currentExpire = parseDateValue(currentExpireVal);
    if (currentExpire && currentExpire.getTime() > now.getTime()) {
      newExpire = new Date(currentExpire.getTime() + daysToAdd * 24 * 60 * 60 * 1000);
    }

    sheet.getRange(rowIndex, 4).setValue(finalTier); // Gói cước
    sheet.getRange(rowIndex, 5).setValue(Utilities.formatDate(newExpire, "GMT+7", "dd/MM/yyyy HH:mm"));  // Ngày hết hạn dạng dd/MM/yyyy HH:mm
    sheet.getRange(rowIndex, 6).setValue('ACTIVE');   // Trạng thái
    sheet.getRange(rowIndex, 7).setValue(transferAmount);
    sheet.getRange(rowIndex, 8).setValue(transactionId);
    sheet.getRange(rowIndex, 9).setValue(`Gia hạn qua SePay lúc ${Utilities.formatDate(now, "GMT+7", "dd/MM/yyyy HH:mm")}`);
  } else {
    // Chưa có -> Tạo dòng mới
    const fullHwid = `AMS-${shortHwid}`;
    sheet.appendRow([
      fullHwid, 'Khách SePay', '', finalTier, Utilities.formatDate(newExpire, "GMT+7", "dd/MM/yyyy HH:mm"), 'ACTIVE', transferAmount, transactionId, `Mua mới qua SePay lúc ${Utilities.formatDate(now, "GMT+7", "dd/MM/yyyy HH:mm")}`
    ]);
  }

  return jsonResponse({
    success: true,
    message: `Đã kích hoạt ${finalTier.toUpperCase()} (+${daysToAdd} ngày) cho mã ${shortHwid}`,
    expire_date: Utilities.formatDate(newExpire, "GMT+7", "dd/MM/yyyy HH:mm")
  });
}

function jsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Tính toán chữ ký số HMAC-SHA256 chuẩn Hex
 */
function computeHmacSha256(message, secret) {
  const rawSig = Utilities.computeHmacSha256Signature(message, secret);
  return rawSig.map(function(byte) {
    var hex = (byte < 0 ? byte + 256 : byte).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  }).join('');
}

// Export hooks cho hệ thống Auto-Loader qua eval()
var handleDoGet = doGet;
var handleDoPost = doPost;
