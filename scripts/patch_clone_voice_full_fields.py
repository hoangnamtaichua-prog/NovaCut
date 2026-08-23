import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_FILE = os.path.join(ROOT_DIR, 'web', 'index.html')

with open(INDEX_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Card 2 inside index.html with all filter fields
old_card2_start = '<!-- Step 2 Card: Voice Metadata -->'
old_card3_start = '<!-- Step 3 Card: Preview Test & Save -->'

start_idx = content.find(old_card2_start)
end_idx = content.find(old_card3_start)

if start_idx == -1 or end_idx == -1:
    print("Could not find Card 2 markers!")
    exit(1)

new_card2 = '''<!-- Step 2 Card: Voice Metadata -->
                    <div class="card settings-card" style="border: 1px solid #334155; border-radius: 12px; background: #0f172a;">
                        <div class="card-header" style="padding: 12px 18px; border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 16px;">🏷️</span>
                                <span style="font-weight: 700; font-size: 13.5px; color: #f8fafc;">2. THÔNG TIN ĐỊNH DANH GIỌNG NÓI</span>
                            </div>
                            <span style="font-size: 11px; color: #38bdf8;">Đầy đủ các trường lọc</span>
                        </div>
                        <div class="card-body" style="padding: 18px; display: flex; flex-direction: column; gap: 14px;">
                            
                            <div class="form-group">
                                <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Tên hiển thị của giọng <span style="color: #ef4444;">*</span></label>
                                <input type="text" id="cloneVoiceName" class="text-input" placeholder="Ví dụ: Giọng Review Phim Đêm Khuya, Idol Nam Thần, Giọng Kể Chuyện..." style="width: 100%; padding: 10px 14px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 13px;">
                            </div>

                            <!-- Row 1: Language, Region, Gender -->
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Ngôn ngữ</label>
                                    <select id="cloneVoiceLang" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                        <option value="Vietnamese" selected>🇻🇳 Tiếng Việt</option>
                                        <option value="English">🇺🇸 Tiếng Anh (English)</option>
                                        <option value="Chinese">🇨🇳 Tiếng Trung</option>
                                        <option value="Japanese">🇯🇵 Tiếng Nhật</option>
                                        <option value="Korean">🇰🇷 Tiếng Hàn</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Vùng miền</label>
                                    <select id="cloneVoiceRegion" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                        <option value="Hà Nội" selected>Bắc (Hà Nội)</option>
                                        <option value="Sài Gòn">Nam (Sài Gòn)</option>
                                        <option value="Huế">Trung (Huế)</option>
                                        <option value="US English">US English</option>
                                        <option value="Toàn quốc">Toàn quốc / Khác</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Giới tính</label>
                                    <select id="cloneVoiceGender" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                        <option value="Female" selected>👩 Nữ</option>
                                        <option value="Male">👨 Nam</option>
                                    </select>
                                </div>
                            </div>

                            <!-- Row 2: Age, Style, Tag -->
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 12px;">
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Độ tuổi</label>
                                    <select id="cloneVoiceAge" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                        <option value="young" selected>🧑 Thanh niên / Trẻ</option>
                                        <option value="middle_aged">👨‍💼 Trung niên</option>
                                        <option value="old">👴 Lớn tuổi</option>
                                        <option value="child">👶 Trẻ em</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Phong cách</label>
                                    <select id="cloneVoiceStyle" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                        <option value="review" selected>🎬 Review phim / Tóm tắt</option>
                                        <option value="story">🎙️ Kể chuyện / Thuyết minh</option>
                                        <option value="news">📰 Thời sự / Phóng sự</option>
                                        <option value="emotional">💖 Tình cảm / Tâm sự</option>
                                        <option value="action">⚡ Kịch tính / Hành động</option>
                                        <option value="anime">🎀 Anime / Độc lạ</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Mô tả / Tag</label>
                                    <input type="text" id="cloneVoiceTag" class="text-input" placeholder="Ví dụ: Giọng trầm ấm, truyền cảm" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                </div>
                            </div>

                        </div>
                    </div>

                    '''

content = content[:start_idx] + new_card2 + content[end_idx:]

# Also append Edit Cloned Voice Modal before </body> if not present
if 'id="modalEditClonedVoice"' not in content:
    modal_code = '''
    <!-- Modal Chỉnh sửa thông tin giọng Clone -->
    <div id="modalEditClonedVoice" class="modal-overlay" style="display: none; position: fixed; inset: 0; background: rgba(0, 0, 0, 0.8); backdrop-filter: blur(6px); z-index: 99999; align-items: center; justify-content: center;">
        <div style="background: #0f172a; border: 1px solid #38bdf8; border-radius: 14px; width: 620px; max-width: 92vw; padding: 22px 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.8), 0 0 20px rgba(56, 189, 248, 0.2); animation: fadeIn 0.2s ease;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; border-bottom: 1px solid #1e293b; padding-bottom: 12px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 22px;">✏️</span>
                    <div>
                        <h3 style="font-size: 16px; font-weight: 700; color: #f8fafc; margin: 0;">CHỈNH SỬA THÔNG TIN GIỌNG NÓI</h3>
                        <div style="font-size: 11.5px; color: #94a3b8; margin-top: 2px;">Cập nhật lại tên, ngôn ngữ, vùng miền, độ tuổi và phong cách</div>
                    </div>
                </div>
                <button type="button" id="btnCloseEditVoiceModal" style="background: none; border: none; color: #94a3b8; font-size: 22px; cursor: pointer; line-height: 1;">&times;</button>
            </div>

            <input type="hidden" id="editVoiceId">

            <div style="display: flex; flex-direction: column; gap: 14px;">
                <div class="form-group">
                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Tên hiển thị của giọng <span style="color: #ef4444;">*</span></label>
                    <input type="text" id="editVoiceName" class="text-input" placeholder="Tên giọng..." style="width: 100%; padding: 10px 14px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 13px;">
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                    <div class="form-group">
                        <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Ngôn ngữ</label>
                        <select id="editVoiceLang" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                            <option value="Vietnamese">🇻🇳 Tiếng Việt</option>
                            <option value="English">🇺🇸 Tiếng Anh</option>
                            <option value="Chinese">🇨🇳 Tiếng Trung</option>
                            <option value="Japanese">🇯🇵 Tiếng Nhật</option>
                            <option value="Korean">🇰🇷 Tiếng Hàn</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Vùng miền</label>
                        <select id="editVoiceRegion" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                            <option value="Hà Nội">Bắc (Hà Nội)</option>
                            <option value="Sài Gòn">Nam (Sài Gòn)</option>
                            <option value="Huế">Trung (Huế)</option>
                            <option value="US English">US English</option>
                            <option value="Toàn quốc">Toàn quốc / Khác</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Giới tính</label>
                        <select id="editVoiceGender" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                            <option value="Female">👩 Nữ</option>
                            <option value="Male">👨 Nam</option>
                        </select>
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                    <div class="form-group">
                        <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Độ tuổi</label>
                        <select id="editVoiceAge" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                            <option value="young">🧑 Thanh niên / Trẻ</option>
                            <option value="middle_aged">👨‍💼 Trung niên</option>
                            <option value="old">👴 Lớn tuổi</option>
                            <option value="child">👶 Trẻ em</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Phong cách</label>
                        <select id="editVoiceStyle" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                            <option value="review">🎬 Review phim</option>
                            <option value="story">🎙️ Kể chuyện</option>
                            <option value="news">📰 Thời sự</option>
                            <option value="emotional">💖 Tình cảm</option>
                            <option value="action">⚡ Kịch tính</option>
                            <option value="anime">🎀 Anime</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Mô tả / Tag</label>
                        <input type="text" id="editVoiceTag" class="text-input" placeholder="Ví dụ: Giọng trầm ấm..." style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                    </div>
                </div>
            </div>

            <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; border-top: 1px solid #1e293b; padding-top: 14px;">
                <button type="button" id="btnCancelEditVoice" class="btn secondary" style="padding: 8px 18px; font-size: 13px;">Hủy</button>
                <button type="button" id="btnSubmitEditVoice" class="btn primary-cyan" style="padding: 8px 22px; font-size: 13px; font-weight: 700; background: linear-gradient(135deg, #0ea5e9, #38bdf8); border: none; color: #0f172a;">💾 CẬP NHẬT THÔNG TIN</button>
            </div>
        </div>
    </div>
'''
    body_close_idx = content.rfind('</body>')
    content = content[:body_close_idx] + modal_code + content[body_close_idx:]

with open(INDEX_FILE, 'w', encoding='utf-8') as f:
    f.write(content)

print("SUCCESS: Updated index.html with all metadata fields and Edit Modal!")
