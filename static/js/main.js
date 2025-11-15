// API接続テスト（設定セクション用）
async function testAPIFromSettings(apiName) {
    try {
        const button = document.getElementById(`${apiName}-test-btn`);
        if (!button) {
            console.error(`ボタンが見つかりません: ${apiName}-test-btn`);
            return;
        }
        
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = 'テスト中...';
        
        // 設定グループ内に結果を表示
        const settingGroup = button.closest('.api-setting-group');
        if (!settingGroup) {
            console.error('設定グループが見つかりません');
            button.disabled = false;
            button.textContent = originalText;
            return;
        }
        
        let resultDiv = settingGroup.querySelector('.api-test-result');
        if (!resultDiv) {
            resultDiv = document.createElement('div');
            resultDiv.className = 'api-test-result';
            settingGroup.appendChild(resultDiv);
        }
        
        resultDiv.innerHTML = '<p style="color: #666;">テスト中...</p>';
        
        try {
            // フォームから値を取得してAPIテストに送信
            let testUrl = `/api/test/${apiName}`;
            const params = new URLSearchParams();
            
            if (apiName === 'chatwork') {
                const apiToken = document.getElementById('chatwork-api-token').value.trim();
                if (apiToken) {
                    params.append('api_token', apiToken);
                }
            } else if (apiName === 'gemini') {
                // Gemini API: フォームの値を直接使用
                const apiKey = document.getElementById('gemini-api-key').value.trim();
                // フォームの値が空の場合は、現在の設定を使用（パラメータを送信しない）
                if (apiKey && apiKey !== '') {
                    params.append('api_key', apiKey);
                }
            } else if (apiName === 'zoom') {
                // Zoom API: フォームの値を直接使用
                const apiKey = document.getElementById('zoom-api-key').value.trim();
                const apiSecret = document.getElementById('zoom-api-secret').value.trim();
                const accountId = document.getElementById('zoom-account-id').value.trim();
                
                // デバッグ用ログ
                console.log(`[${apiName}] フォームの値:`, {
                    apiKey: apiKey ? `${apiKey.substring(0, 5)}...${apiKey.substring(apiKey.length - 5)} (長さ: ${apiKey.length})` : '(空)',
                    apiSecret: apiSecret ? `${apiSecret.substring(0, 5)}...${apiSecret.substring(apiSecret.length - 5)} (長さ: ${apiSecret.length})` : '(空)',
                    accountId: accountId || '(空)'
                });
                
                // 警告: api_secretがapi_keyと同じ値の場合は警告を表示
                if (apiKey && apiSecret && apiKey === apiSecret) {
                    console.warn(`[${apiName}] ⚠️ 警告: API SecretがAPI Keyと同じ値になっています！フォームをクリアしてください。`);
                }
                
                // フォームの値が空の場合は、現在の設定を使用（パラメータを送信しない）
                // 重要: フォームに値が入力されている場合のみパラメータを送信
                // プレースホルダーが「設定済み」の場合は、フォームの値は空なので、設定ファイルから読み込む
                if (apiKey && apiKey !== '' && apiKey !== '設定済み（更新する場合は入力）') {
                    params.append('api_key', apiKey);
                }
                if (apiSecret && apiSecret !== '' && apiSecret !== '設定済み（更新する場合は入力）') {
                    params.append('api_secret', apiSecret);
                }
                if (accountId && accountId !== '' && accountId !== '設定済み（更新する場合は入力）') {
                    params.append('account_id', accountId);
                }
            }
            
            // パラメータがある場合のみクエリ文字列を追加
            if (params.toString()) {
                testUrl += '?' + params.toString();
            }
            
            console.log(`[${apiName}] API接続テスト開始: ${testUrl}`);
            
            const response = await fetch(testUrl);
            
            // レスポンスのステータスコードを確認
            if (!response.ok) {
                // 429エラー（レート制限）の場合は、レスポンスボディから詳細なメッセージを取得
                if (response.status === 429) {
                    try {
                        const errorData = await response.json();
                        if (errorData.message) {
                            // エラーメッセージをそのまま表示
                            resultDiv.className = 'api-test-result error';
                            const errorMessage = errorData.message.replace(/\n/g, '<br>');
                            resultDiv.innerHTML = `<p style="color: #991B1B; font-weight: 500;">❌ ${errorMessage}</p>`;
                            button.disabled = false;
                            button.textContent = originalText;
                            return;
                        }
                    } catch (e) {
                        // JSONパースに失敗した場合は、テキストとして表示
                        const errorText = await response.text();
                        resultDiv.className = 'api-test-result error';
                        resultDiv.innerHTML = `<p style="color: #991B1B; font-weight: 500;">❌ Gemini API接続失敗: クォータ制限に達しています。しばらく待ってから再度お試しください。</p>`;
                        button.disabled = false;
                        button.textContent = originalText;
                        return;
                    }
                }
                // その他のHTTPエラーの場合
                const errorText = await response.text();
                console.error(`[${apiName}] HTTPエラー: ${response.status} ${response.statusText}`, errorText);
                throw new Error(`HTTPエラー: ${response.status} ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // デバッグ用ログ
            console.log(`[${apiName}] API接続テスト結果:`, data);
            
            if (data.success) {
                resultDiv.className = 'api-test-result success';
                let message = `✅ ${data.message}`;
                
                // Chatwork APIの場合は詳細情報を表示
                if (apiName === 'chatwork' && data.account_info) {
                    message += `<br><small style="opacity: 0.8;">アカウント: ${data.account_info.name || 'N/A'}</small>`;
                }
                
                resultDiv.innerHTML = `<p style="color: #065F46; font-weight: 500;">${message}</p>`;
            } else {
                resultDiv.className = 'api-test-result error';
                // エラーメッセージの改行を<br>に変換
                const errorMessage = data.message.replace(/\n/g, '<br>');
                resultDiv.innerHTML = `<p style="color: #991B1B; font-weight: 500;">❌ ${errorMessage}</p>`;
            }
        } catch (error) {
            console.error(`[${apiName}] API接続テストエラー:`, error);
            resultDiv.className = 'api-test-result error';
            let errorMessage = error.message;
            // ネットワークエラーの場合は詳細を表示
            if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                errorMessage = 'ネットワークエラーが発生しました。アプリケーションが起動しているか確認してください。';
            }
            resultDiv.innerHTML = `<p style="color: #991B1B; font-weight: 500;">❌ エラー: ${errorMessage}</p>`;
        } finally {
            button.disabled = false;
            button.textContent = originalText;
            
            // 5秒後に結果を非表示
            setTimeout(() => {
                if (resultDiv && resultDiv.parentNode) {
                    resultDiv.style.opacity = '0';
                    setTimeout(() => {
                        if (resultDiv && resultDiv.parentNode) {
                            resultDiv.remove();
                        }
                    }, 300);
                }
            }, 5000);
        }
    } catch (error) {
        console.error('testAPIFromSettingsエラー:', error);
        alert(`エラーが発生しました: ${error.message}`);
    }
}

// グローバルスコープに確実に配置
window.testAPIFromSettings = testAPIFromSettings;

// テストボタンのイベントリスナーを設定
function setupTestButtons() {
    console.log('setupTestButtons() が呼び出されました');
    
    // 設定セクションの接続テストボタン
    const settingTestButtons = document.querySelectorAll('.btn-test-small[data-api]');
    console.log(`接続テストボタンを検出: ${settingTestButtons.length}個`);
    
    settingTestButtons.forEach((button, index) => {
        const apiName = button.getAttribute('data-api');
        console.log(`ボタン ${index + 1}: API=${apiName}, ID=${button.id}`);
        
        // 既存のイベントリスナーを削除（重複を防ぐ）
        const newButton = button.cloneNode(true);
        button.parentNode.replaceChild(newButton, button);
        
        newButton.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log(`接続テストボタンがクリックされました: API=${apiName}`);
            testAPIFromSettings(apiName);
        });
    });
    
    // ChatworkルームID検証ボタン
    const chatworkRoomTestBtn = document.getElementById('chatwork-room-test-btn');
    if (chatworkRoomTestBtn) {
        console.log('ChatworkルームID検証ボタンを検出');
        
        // 既存のイベントリスナーを削除（重複を防ぐ）
        const newBtn = chatworkRoomTestBtn.cloneNode(true);
        chatworkRoomTestBtn.parentNode.replaceChild(newBtn, chatworkRoomTestBtn);
        
        newBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('ChatworkルームID検証ボタンがクリックされました');
            testChatworkRoomFromSettings();
        });
    } else {
        console.warn('ChatworkルームID検証ボタンが見つかりません');
    }
}

function getAPIName(apiName) {
    const names = {
        'zoom': 'Zoom API',
        'gemini': 'Gemini API',
        'chatwork': 'Chatwork API'
    };
    return names[apiName] || apiName;
}

// フォーム送信処理（DOMContentLoaded内で設定）
function setupProcessForm() {
    console.log('setupProcessForm() が呼び出されました');
    const processForm = document.getElementById('process-form');
    if (!processForm) {
        console.warn('process-formが見つかりません');
        return;
    }
    
    console.log('process-formのイベントリスナーを設定します');
    processForm.addEventListener('submit', async (e) => {
        console.log('議事録生成フォームが送信されました');
        e.preventDefault();
        
        const meetingId = document.getElementById('meeting-id').value.trim();
        const roomId = document.getElementById('room-id').value.trim();
        const submitBtn = document.getElementById('submit-btn');
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoader = submitBtn.querySelector('.btn-loader');
        const progressSection = document.getElementById('progress-section');
        const resultSection = document.getElementById('result-section');
        
        // 入力値の検証
        if (!meetingId) {
            alert('ミーティングIDを入力してください');
            return;
        }
        
        if (!roomId) {
            alert('ChatworkルームIDを入力してください');
            return;
        }
        
        // デバッグ用ログ
        console.log(`議事録生成を開始: ミーティングID=${meetingId} (型: ${typeof meetingId}), ルームID=${roomId}`);
        
        // ボタンを無効化
        submitBtn.disabled = true;
        btnText.style.display = 'none';
        btnLoader.style.display = 'inline';
        
        // 結果セクションを非表示
        resultSection.style.display = 'none';
        
        // 進捗セクションを表示
        progressSection.style.display = 'block';
        
        try {
            // 処理を開始
            const startResponse = await fetch('/api/process', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    meeting_id: String(meetingId),  // 明示的に文字列に変換
                    room_id: String(roomId)  // 明示的に文字列に変換
                })
            });
            
            const startData = await startResponse.json();
            const taskId = startData.task_id;
            
            // 進捗をポーリング
            const pollInterval = setInterval(async () => {
                try {
                    const statusResponse = await fetch(`/api/status/${taskId}`);
                    if (!statusResponse.ok) {
                        if (statusResponse.status === 404) {
                            // タスクが見つからない場合、少し待ってから再試行
                            console.warn(`タスク ${taskId} が見つかりません。再試行します...`);
                            return;
                        }
                        throw new Error(`HTTPエラー: ${statusResponse.status} ${statusResponse.statusText}`);
                    }
                    const statusData = await statusResponse.json();
                    
                    // 進捗を更新
                    const progressFill = document.getElementById('progress-fill');
                    const progressMessage = document.getElementById('progress-message');
                    
                    progressFill.style.width = `${statusData.progress}%`;
                    progressFill.textContent = `${statusData.progress}%`;
                    progressMessage.textContent = statusData.message || '処理中...';
                    
                    // 完了またはエラー時
                    if (statusData.status === 'completed' || statusData.status === 'error') {
                        clearInterval(pollInterval);
                        
                        // 進捗セクションを非表示
                        progressSection.style.display = 'none';
                        
                        // 結果セクションを表示
                        resultSection.style.display = 'block';
                        displayResult(statusData.result);
                        
                        // ボタンを有効化
                        submitBtn.disabled = false;
                        btnText.style.display = 'inline';
                        btnLoader.style.display = 'none';
                    }
                } catch (error) {
                    clearInterval(pollInterval);
                    displayError(`進捗取得エラー: ${error.message}`);
                    submitBtn.disabled = false;
                    btnText.style.display = 'inline';
                    btnLoader.style.display = 'none';
                }
            }, 1000); // 1秒ごとにポーリング
            
        } catch (error) {
            displayError(`処理開始エラー: ${error.message}`);
            submitBtn.disabled = false;
            btnText.style.display = 'inline';
            btnLoader.style.display = 'none';
            progressSection.style.display = 'none';
        }
    });
}

// 結果表示
function displayResult(result) {
    const resultContent = document.getElementById('result-content');
    
    if (result.success) {
        resultContent.innerHTML = `
            <div class="result-success">
                <span>✅</span>
                <span>議事録の生成と送信が完了しました！</span>
            </div>
            <div style="margin-top: 15px; color: var(--text-secondary);">
                <p><strong>ミーティングID:</strong> ${result.meeting_id}</p>
                <p><strong>送信先ルームID:</strong> ${result.room_id}</p>
            </div>
            ${result.transcript ? `
                <div class="result-transcript">
                    <strong>生成された議事録:</strong>
                    <pre>${escapeHtml(result.transcript)}</pre>
                </div>
            ` : ''}
        `;
    } else {
        resultContent.innerHTML = `
            <div class="result-error">
                <span>❌</span>
                <span>エラーが発生しました</span>
            </div>
            <div style="margin-top: 15px; color: var(--danger-color);">
                <p>${escapeHtml(result.error || '不明なエラー')}</p>
            </div>
        `;
    }
}

// エラー表示
function displayError(message) {
    const resultSection = document.getElementById('result-section');
    const resultContent = document.getElementById('result-content');
    
    resultSection.style.display = 'block';
    resultContent.innerHTML = `
        <div class="result-error">
            <span>❌</span>
            <span>エラーが発生しました</span>
        </div>
        <div style="margin-top: 15px; color: var(--danger-color);">
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}

// HTMLエスケープ
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 最近のミーティングを取得（自動処理設定用）
// グローバルスコープに確実に配置
window.loadRecentMeetings = async function loadRecentMeetings() {
    const container = document.getElementById('meetings-container');
    const section = document.getElementById('recent-meetings');
    
    container.innerHTML = '<p>取得中...</p>';
    section.style.display = 'block';
    
    try {
        const response = await fetch('/api/meetings/recent');
        const data = await response.json();
        
        if (data.success && data.meetings && data.meetings.length > 0) {
            let html = '<div class="meetings-grid">';
            data.meetings.forEach(meeting => {
                const meetingId = meeting.id;
                const topic = meeting.topic || 'タイトルなし';
                const startTime = meeting.start_time ? new Date(meeting.start_time).toLocaleString('ja-JP') : '不明';
                
                html += `
                    <div class="meeting-card">
                        <h4>${escapeHtml(topic)}</h4>
                        <p><strong>ミーティングID:</strong> ${meetingId}</p>
                        <p><strong>開始時刻:</strong> ${startTime}</p>
                        <div class="meeting-actions">
                            <input type="text" id="room-id-${meetingId}" placeholder="ChatworkルームID（例: 12345678）" class="form-input" style="margin-bottom: 10px;">
                            <small style="display: block; margin-bottom: 10px; color: #666; font-size: 0.85em;">
                                ルームIDはルーム設定画面またはURLから確認できます<br>
                                <span style="color: #ff6b6b;">※ 管理者のみ確認可能です</span>
                            </small>
                            <button class="btn btn-small" onclick="addAutoProcessMapping('${meetingId}', '${escapeHtml(topic)}')">
                                自動処理を設定
                            </button>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<p class="empty-message">録画付きミーティングが見つかりませんでした。</p>';
        }
    } catch (error) {
        container.innerHTML = `<p class="error-message">エラー: ${error.message}</p>`;
    }
}

// 最近のミーティングを取得（手動処理用）
// グローバルスコープに確実に配置
window.loadRecentMeetingsForManual = async function loadRecentMeetingsForManual() {
    const container = document.getElementById('manual-meetings-container');
    const section = document.getElementById('manual-meetings-list');
    
    container.innerHTML = '<p>取得中...</p>';
    section.style.display = 'block';
    
    try {
        const response = await fetch('/api/meetings/recent');
        
        // レスポンスのステータスを確認
        if (!response.ok) {
            throw new Error(`HTTPエラー: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // デバッグ用ログ
        console.log('APIレスポンス:', {
            success: data.success,
            meetingsCount: data.meetings ? data.meetings.length : 0,
            totalCount: data.count || 0,
            hasError: !!data.message,
            errorMessage: data.message
        });
        
        if (data.success && data.meetings && data.meetings.length > 0) {
            // ミーティングを日付順にソート（新しい順）
            const sortedMeetings = [...data.meetings].sort((a, b) => {
                const dateA = a.start_time ? new Date(a.start_time).getTime() : 0;
                const dateB = b.start_time ? new Date(b.start_time).getTime() : 0;
                return dateB - dateA; // 新しい順
            });
            
            // 日付別にグループ化
            const meetingsByDate = {};
            sortedMeetings.forEach(meeting => {
                const startDate = meeting.start_time ? meeting.start_time.substring(0, 10) : '不明';
                if (!meetingsByDate[startDate]) {
                    meetingsByDate[startDate] = [];
                }
                meetingsByDate[startDate].push(meeting);
            });
            
            // 日付順にソート（新しい順）
            const sortedDates = Object.keys(meetingsByDate).sort((a, b) => {
                if (a === '不明') return 1;
                if (b === '不明') return -1;
                return new Date(b) - new Date(a);
            });
            
            let html = '<div style="display: grid; gap: 20px;">';
            
            // 日付別に表示
            sortedDates.forEach(date => {
                const dateMeetings = meetingsByDate[date];
                const dateLabel = date === '不明' ? '日時不明' : new Date(date + 'T00:00:00').toLocaleDateString('ja-JP', { 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric',
                    weekday: 'short'
                });
                
                html += `
                    <div style="border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; margin-bottom: 10px;">
                        <h3 style="margin: 0 0 10px 0; color: #374151; font-size: 16px; font-weight: bold;">
                            📅 ${dateLabel} (${dateMeetings.length}件)
                        </h3>
                        <div style="display: grid; gap: 10px;">
                `;
                
                dateMeetings.forEach(meeting => {
                    // ミーティングIDを明示的に文字列に変換
                    const meetingId = String(meeting.id || '');
                    const topic = meeting.topic || 'タイトルなし';
                    const startTime = meeting.start_time ? new Date(meeting.start_time).toLocaleString('ja-JP') : '不明';
                    const startDate = meeting.start_time ? meeting.start_time.substring(0, 10) : '';
                    const isLocalRecording = meeting.is_local_recording || false;
                    const recordings = meeting.recordings || [];
                    const recordingType = isLocalRecording ? 'コンピュータ録画' : 'クラウド録画';
                    
                    // 6月期のミーティングかどうかを判定
                    const isJune = startDate.startsWith('2025-06') || startDate.startsWith('2024-06');
                    
                    // 録画情報を表示
                    let recordingInfo = '';
                    if (recordings.length > 0) {
                        const firstRec = recordings[0];
                        const fileType = firstRec.file_type || 'N/A';
                        const fileSize = firstRec.file_size ? (firstRec.file_size / 1024 / 1024).toFixed(2) + ' MB' : 'N/A';
                        recordingInfo = `<br><small style="color: #059669;">📹 ${recordingType} | ${fileType} (${fileSize})</small>`;
                    }
                    
                    html += `
                        <div style="padding: 12px; background: white; border-radius: 6px; border: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center; ${isJune ? 'border-left: 4px solid #3B82F6;' : ''} ${isLocalRecording ? 'border-top: 3px solid #10B981;' : ''}">
                            <div style="flex: 1;">
                                <strong>${escapeHtml(topic)}</strong><br>
                                <small style="color: #666;">ID: ${meetingId} | 開始: ${startTime}</small>
                                ${recordingInfo}
                                ${isJune ? '<br><small style="color: #3B82F6; font-weight: bold;">📅 6月期のミーティング</small>' : ''}
                                ${isLocalRecording ? '<br><small style="color: #059669; font-weight: bold;">💾 コンピュータ録画</small>' : ''}
                            </div>
                            <button class="btn btn-small" onclick="selectMeetingForManual('${meetingId}')" style="margin-left: 10px;">
                                選択
                            </button>
                        </div>
                    `;
                });
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            container.innerHTML = html;
            
            // 6月期のミーティング数を表示
            const juneCount = sortedMeetings.filter(m => {
                const startDate = m.start_time ? m.start_time.substring(0, 10) : '';
                return startDate.startsWith('2025-06') || startDate.startsWith('2024-06');
            }).length;
            
            if (juneCount > 0) {
                const infoDiv = document.createElement('div');
                infoDiv.style.cssText = 'margin-top: 10px; padding: 10px; background: #EFF6FF; border-radius: 6px; border: 1px solid #3B82F6;';
                infoDiv.innerHTML = `<small style="color: #1E40AF;">📅 6月期のミーティング: ${juneCount}件</small>`;
                container.appendChild(infoDiv);
            }
        } else {
            // エラーメッセージを詳細に表示
            let errorMessage = '録画付きミーティングが見つかりませんでした。';
            if (!data.success && data.message) {
                errorMessage = `エラーが発生しました: ${escapeHtml(data.message)}`;
                container.className = 'error-message';
            } else if (data.meetings && data.meetings.length === 0) {
                errorMessage += '<br><small style="color: #666;">（ミーティングは0件です）</small>';
            }
            container.innerHTML = `<p class="empty-message">${errorMessage}</p>`;
        }
    } catch (error) {
        console.error('ミーティング取得エラー:', error);
        container.innerHTML = `<p class="error-message">エラー: ${escapeHtml(error.message)}<br><small>ブラウザのコンソールを確認してください。</small></p>`;
    }
}

// 手動処理用にミーティングを選択
// グローバルスコープに確実に配置
window.selectMeetingForManual = function selectMeetingForManual(meetingId) {
    // ミーティングIDを文字列に変換して設定
    const meetingIdStr = String(meetingId).trim();
    document.getElementById('meeting-id').value = meetingIdStr;
    document.getElementById('manual-meetings-list').style.display = 'none';
    
    // デバッグ用ログ
    console.log(`ミーティングを選択しました: ID=${meetingIdStr} (型: ${typeof meetingIdStr})`);
    
    // フォームにフォーカスを移動
    document.getElementById('room-id').focus();
}

// ChatworkルームID検証（設定セクション用）
async function testChatworkRoomFromSettings() {
    try {
        const button = document.getElementById('chatwork-room-test-btn');
        if (!button) {
            console.error('chatwork-room-test-btnが見つかりません');
            return;
        }
        
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = '検証中...';
        
        // 設定グループ内に結果を表示
        const settingGroup = button.closest('.api-setting-group');
        if (!settingGroup) {
            console.error('設定グループが見つかりません');
            button.disabled = false;
            button.textContent = originalText;
            return;
        }
        
        let resultDiv = settingGroup.querySelector('.api-test-result');
        if (!resultDiv) {
            resultDiv = document.createElement('div');
            resultDiv.className = 'api-test-result';
            settingGroup.appendChild(resultDiv);
        }
        
        resultDiv.innerHTML = '<p style="color: #666;">検証中...</p>';
        
        // フォームから値を取得
        const apiToken = document.getElementById('chatwork-api-token').value.trim();
        const roomId = document.getElementById('default-chatwork-room-id').value.trim();
        
        if (!apiToken) {
            resultDiv.className = 'api-test-result error';
            resultDiv.innerHTML = '<p style="color: #991B1B; font-weight: 500;">❌ APIトークンが入力されていません</p>';
            button.disabled = false;
            button.textContent = originalText;
            return;
        }
        
        if (!roomId) {
            resultDiv.className = 'api-test-result error';
            resultDiv.innerHTML = '<p style="color: #991B1B; font-weight: 500;">❌ ルームIDが入力されていません</p>';
            button.disabled = false;
            button.textContent = originalText;
            return;
        }
        
        try {
            const response = await fetch(`/api/test/chatwork-room?api_token=${encodeURIComponent(apiToken)}&room_id=${encodeURIComponent(roomId)}`);
            const data = await response.json();
            
            if (data.success) {
                resultDiv.className = 'api-test-result success';
                resultDiv.innerHTML = `<p style="color: #065F46; font-weight: 500;">✅ ${data.message}</p>`;
            } else {
                resultDiv.className = 'api-test-result error';
                resultDiv.innerHTML = `<p style="color: #991B1B; font-weight: 500;">❌ ${data.message}</p>`;
            }
        } catch (error) {
            resultDiv.className = 'api-test-result error';
            resultDiv.innerHTML = `<p style="color: #991B1B; font-weight: 500;">❌ エラー: ${error.message}</p>`;
        } finally {
            button.disabled = false;
            button.textContent = originalText;
            
            // 5秒後に結果を非表示
            setTimeout(() => {
                if (resultDiv && resultDiv.parentNode) {
                    resultDiv.style.opacity = '0';
                    setTimeout(() => {
                        if (resultDiv && resultDiv.parentNode) {
                            resultDiv.remove();
                        }
                    }, 300);
                }
            }, 5000);
        }
    } catch (error) {
        console.error('testChatworkRoomFromSettingsエラー:', error);
        alert(`エラーが発生しました: ${error.message}`);
    }
}

// 自動処理マッピングを追加
// グローバルスコープに確実に配置
window.addAutoProcessMapping = async function addAutoProcessMapping(meetingId, meetingTopic) {
    const roomIdInput = document.getElementById(`room-id-${meetingId}`);
    const roomId = roomIdInput.value.trim();
    
    if (!roomId) {
        alert('ChatworkルームIDを入力してください\n\nルームIDの確認方法:\n• ルーム右上の⚙️アイコン → 「グループチャットの設定」→ 下部の「ルームID」\n• または、ルームのURL末尾の数字（例: #!rid12345678 の場合、12345678）\n\n※ ルームIDは管理者のみ確認可能です');
        return;
    }
    
    try {
        const formData = new URLSearchParams();
        formData.append('meeting_id', meetingId);
        formData.append('room_id', roomId);
        formData.append('meeting_topic', meetingTopic);
        
        const response = await fetch('/api/auto-process/mapping', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('自動処理設定を追加しました！');
            roomIdInput.value = '';
            loadAutoProcessMappings();
        } else {
            alert(`エラー: ${data.message}`);
        }
    } catch (error) {
        alert(`エラー: ${error.message}`);
    }
}

// 自動処理マッピング一覧を取得
// グローバルスコープに確実に配置
window.loadAutoProcessMappings = async function loadAutoProcessMappings() {
    const container = document.getElementById('mappings-container');
    
    try {
        const response = await fetch('/api/auto-process/mappings');
        const data = await response.json();
        
        if (data.success && data.mappings && Object.keys(data.mappings).length > 0) {
            let html = '<div class="mappings-grid">';
            Object.entries(data.mappings).forEach(([meetingId, config]) => {
                const processed = config.processed ? '✅ 処理済み' : '⏳ 待機中';
                const processedAt = config.processed_at ? new Date(config.processed_at).toLocaleString('ja-JP') : '';
                
                html += `
                    <div class="mapping-card">
                        <h4>${escapeHtml(config.meeting_topic || 'タイトルなし')}</h4>
                        <p><strong>ミーティングID:</strong> ${meetingId}</p>
                        <p><strong>ChatworkルームID:</strong> ${config.room_id}</p>
                        <p><strong>ステータス:</strong> ${processed}</p>
                        ${processedAt ? `<p><strong>処理日時:</strong> ${processedAt}</p>` : ''}
                        <button class="btn btn-small btn-danger" onclick="removeAutoProcessMapping('${meetingId}')">
                            削除
                        </button>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<p class="empty-message">設定がありません。上記の「最近のミーティングを取得」から設定を追加してください。</p>';
        }
    } catch (error) {
        container.innerHTML = `<p class="error-message">エラー: ${error.message}</p>`;
    }
}

// 自動処理マッピングを削除
// グローバルスコープに確実に配置
window.removeAutoProcessMapping = async function removeAutoProcessMapping(meetingId) {
    if (!confirm('この自動処理設定を削除しますか？')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/auto-process/mapping/${meetingId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('自動処理設定を削除しました');
            loadAutoProcessMappings();
        } else {
            alert(`エラー: ${data.message}`);
        }
    } catch (error) {
        alert(`エラー: ${error.message}`);
    }
}

// API設定フォームの送信処理（DOMContentLoaded内で設定）
function setupAPISettingsForm() {
    console.log('setupAPISettingsForm() が呼び出されました');
    const form = document.getElementById('api-settings-form');
    if (!form) {
        console.warn('api-settings-formが見つかりません');
        return;
    }
    
    console.log('api-settings-formのイベントリスナーを設定します');
    form.addEventListener('submit', async (e) => {
        console.log('API設定フォームが送信されました');
        e.preventDefault();
        
        const form = e.target;
        const formData = new FormData(form);
        const saveBtn = document.getElementById('save-api-settings-btn');
        const btnText = saveBtn.querySelector('.btn-text');
        const originalText = btnText.textContent;
        
        // 必須項目のチェック（既存の設定がある場合は必須ではない）
        // 空の値が送信された場合、サーバー側で既存の値を保持する
        // ただし、初回設定時は必須項目をチェック
        const zoomApiKey = formData.get('zoom_api_key');
        const zoomApiSecret = formData.get('zoom_api_secret');
        const geminiApiKey = formData.get('gemini_api_key');
        const chatworkApiToken = formData.get('chatwork_api_token');
        
        // プレースホルダーから既存の設定があるかどうかを確認
        const zoomApiKeyEl = document.getElementById('zoom-api-key');
        const geminiApiKeyEl = document.getElementById('gemini-api-key');
        const chatworkApiTokenEl = document.getElementById('chatwork-api-token');
        
        const hasExistingZoom = zoomApiKeyEl && zoomApiKeyEl.placeholder.includes('設定済み');
        const hasExistingGemini = geminiApiKeyEl && geminiApiKeyEl.placeholder.includes('設定済み');
        const hasExistingChatwork = chatworkApiTokenEl && chatworkApiTokenEl.placeholder.includes('設定済み');
        
        // 初回設定時のみ必須チェック（既存の設定がない場合）
        if (!hasExistingZoom && (!zoomApiKey || !zoomApiSecret)) {
            alert('Zoom API設定: API KeyとAPI Secretは必須です（初回設定時）');
            return;
        }
        
        if (!hasExistingGemini && !geminiApiKey) {
            alert('Gemini API設定: API Keyは必須です（初回設定時）');
            return;
        }
        
        if (!hasExistingChatwork && !chatworkApiToken) {
            alert('Chatwork API設定: API Tokenは必須です（初回設定時）');
            return;
        }
        
        // ボタンを無効化
        saveBtn.disabled = true;
        btnText.textContent = '💾 保存中...';
        
        try {
            const response = await fetch('/api/settings/save', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                // 成功メッセージを表示（各API設定グループ内に表示）
                // 自動的に各APIの接続テストを実行して結果を表示
                
                // フォームのパスワードフィールドをクリア（値は保存済み）
                // 重要: フォームに古い値が残っていると、それが接続テストに使用されるため、必ずクリアする
                const zoomApiKeyInput = document.getElementById('zoom-api-key');
                const zoomApiSecretInput = document.getElementById('zoom-api-secret');
                const zoomAccountIdInput = document.getElementById('zoom-account-id');
                const geminiApiKeyInput = document.getElementById('gemini-api-key');
                const chatworkApiTokenInput = document.getElementById('chatwork-api-token');
                
                if (zoomApiKeyInput) {
                    zoomApiKeyInput.value = '';
                    zoomApiKeyInput.placeholder = '設定済み（更新する場合は入力）';
                }
                if (zoomApiSecretInput) {
                    zoomApiSecretInput.value = '';
                    zoomApiSecretInput.placeholder = '設定済み（更新する場合は入力）';
                }
                if (zoomAccountIdInput) {
                    zoomAccountIdInput.value = '';
                    zoomAccountIdInput.placeholder = '設定済み（更新する場合は入力）';
                }
                if (geminiApiKeyInput) {
                    geminiApiKeyInput.value = '';
                    geminiApiKeyInput.placeholder = '設定済み（更新する場合は入力）';
                }
                if (chatworkApiTokenInput) {
                    chatworkApiTokenInput.value = '';
                    chatworkApiTokenInput.placeholder = '設定済み（更新する場合は入力）';
                }
                
                // 自動的に各APIの接続テストを実行（設定から読み込んだ値を使用）
                // フォームの値はクリアされているため、設定から読み込んだ値でテスト
                setTimeout(() => {
                    // 設定保存後は、フォームの値ではなく設定から読み込んだ値でテスト
                    // パラメータを送信しない = 現在の設定を使用
                    testAPIFromSettings('zoom');
                    setTimeout(() => testAPIFromSettings('gemini'), 500);
                    setTimeout(() => testAPIFromSettings('chatwork'), 1000);
                }, 1000);
            } else {
                alert(`エラー: ${data.message}`);
            }
        } catch (error) {
            alert(`エラー: ${error.message}`);
        } finally {
            saveBtn.disabled = false;
            btnText.textContent = originalText;
        }
    });
}

// ページ読み込み時に設定を読み込む
async function loadAPISettings() {
    try {
        const response = await fetch('/api/settings/load');
        if (!response.ok) {
            console.warn('設定の読み込みに失敗:', response.status);
            return;
        }
        
        const data = await response.json();
        
        if (data.success && data.settings) {
            const settings = data.settings;
            
            // 設定値が存在する場合はプレースホルダーを更新
            try {
                const zoomApiKeyEl = document.getElementById('zoom-api-key');
                if (zoomApiKeyEl && settings.zoom_api_key) {
                    zoomApiKeyEl.placeholder = '設定済み（更新する場合は入力）';
                }
                
                const zoomApiSecretEl = document.getElementById('zoom-api-secret');
                if (zoomApiSecretEl && settings.zoom_api_secret) {
                    zoomApiSecretEl.placeholder = '設定済み（更新する場合は入力）';
                }
                
                const zoomAccountIdEl = document.getElementById('zoom-account-id');
                if (zoomAccountIdEl && settings.zoom_account_id) {
                    zoomAccountIdEl.value = settings.zoom_account_id;
                }
                
                const geminiApiKeyEl = document.getElementById('gemini-api-key');
                if (geminiApiKeyEl && settings.gemini_api_key) {
                    geminiApiKeyEl.placeholder = '設定済み（更新する場合は入力）';
                }
                
                const chatworkApiTokenEl = document.getElementById('chatwork-api-token');
                if (chatworkApiTokenEl && settings.chatwork_api_token) {
                    chatworkApiTokenEl.placeholder = '設定済み（更新する場合は入力）';
                }
                
                const defaultRoomIdEl = document.getElementById('default-chatwork-room-id');
                if (defaultRoomIdEl && settings.default_chatwork_room_id) {
                    defaultRoomIdEl.value = settings.default_chatwork_room_id;
                }
            } catch (domError) {
                console.warn('DOM要素の更新に失敗:', domError);
            }
        }
    } catch (error) {
        console.error('設定の読み込みに失敗:', error);
    }
}

// ページ読み込み時に自動処理設定とAPI設定を読み込む
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoadedイベントが発火しました');
    try {
        // テストボタンのイベントリスナーを設定
        console.log('setupTestButtons() を呼び出します');
        setupTestButtons();
        
        // フォームのイベントリスナーを設定
        console.log('setupProcessForm() を呼び出します');
        setupProcessForm();
        
        console.log('setupAPISettingsForm() を呼び出します');
        setupAPISettingsForm();
        
        // 設定を読み込む
        console.log('loadAutoProcessMappings() を呼び出します');
        loadAutoProcessMappings();
        
        console.log('loadAPISettings() を呼び出します');
        loadAPISettings();
        
        console.log('初期化が完了しました');
    } catch (error) {
        console.error('DOMContentLoadedエラー:', error);
        console.error('エラーの詳細:', error.stack);
    }
});

// DOMContentLoadedが既に発火している場合のフォールバック
if (document.readyState === 'loading') {
    // DOMContentLoadedを待つ（上記のコードで処理される）
    console.log('DOMContentLoadedを待機中...');
} else {
    // DOMContentLoadedが既に発火している場合は即座に実行
    console.log('DOMContentLoadedは既に発火済み。即座に初期化を実行します');
    try {
        setupTestButtons();
        setupProcessForm();
        setupAPISettingsForm();
        loadAutoProcessMappings();
        loadAPISettings();
    } catch (error) {
        console.error('即座実行エラー:', error);
    }
}

