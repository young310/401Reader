/**
 * 扣繳憑單編輯功能除錯工具
 * 在瀏覽器 Console 中使用
 */

window.TaxOcrDebug = {
    
    /**
     * 檢查當前表格資料的完整性
     */
    checkTableData: function() {
        console.log('=== 表格資料完整性檢查 ===');
        
        if (typeof currentTableData === 'undefined') {
            console.error('❌ currentTableData 未定義');
            return;
        }
        
        console.log('📊 基本統計:');
        console.log('  - 總記錄數:', currentTableData.length);
        
        // 按 jobId 分組統計
        const jobStats = {};
        let missingJobId = 0;
        
        currentTableData.forEach((record, index) => {
            if (!record.jobId) {
                missingJobId++;
                console.warn(`  - 記錄 ${index} 缺少 jobId:`, record);
            } else {
                jobStats[record.jobId] = (jobStats[record.jobId] || 0) + 1;
            }
        });
        
        console.log('  - 按 Job ID 分組:', jobStats);
        console.log('  - 缺少 jobId 的記錄:', missingJobId);
        
        // 按頁碼分組統計
        const pageStats = {};
        currentTableData.forEach((record) => {
            const pageNum = record.頁碼 || 1;
            pageStats[pageNum] = (pageStats[pageNum] || 0) + 1;
        });
        console.log('  - 按頁碼分組:', pageStats);
        
        // 檢查金額異常
        let zeroAmounts = 0;
        let negativeAmounts = 0;
        
        currentTableData.forEach((record, index) => {
            if (record.totalAmount === 0) {
                zeroAmounts++;
            }
            if (record.totalAmount < 0) {
                negativeAmounts++;
                console.warn(`  - 記錄 ${index} 金額為負數:`, record.totalAmount);
            }
        });
        
        console.log('  - 金額為 0 的記錄:', zeroAmounts);
        console.log('  - 金額為負數的記錄:', negativeAmounts);
        
        return {
            totalRecords: currentTableData.length,
            jobStats: jobStats,
            pageStats: pageStats,
            missingJobId: missingJobId,
            zeroAmounts: zeroAmounts,
            negativeAmounts: negativeAmounts
        };
    },
    
    /**
     * 檢查多頁資料的完整性
     */
    checkMultiPageData: function() {
        console.log('=== 多頁資料完整性檢查 ===');
        
        if (typeof allJobs === 'undefined') {
            console.error('❌ allJobs 未定義');
            return;
        }
        
        allJobs.forEach((job, jobIndex) => {
            if (!job.result_json) return;
            
            const json = job.result_json;
            console.log(`📄 Job ${job.id} (${job.original_filename}):`);
            
            if (json.頁面資料 && Array.isArray(json.頁面資料)) {
                console.log(`  多頁格式: ${json.頁面資料.length} 頁`);
                
                json.頁面資料.forEach((page, pageIndex) => {
                    const recordCount = page.records ? page.records.length : 0;
                    const pageNum = page.頁碼 || (pageIndex + 1);
                    
                    console.log(`    第 ${pageNum} 頁: ${recordCount} 筆記錄`);
                    
                    if (page.records && page.records.length > 0) {
                        page.records.forEach((record, recordIndex) => {
                            if (recordIndex < 2) { // 只顯示前2筆
                                console.log(`      - ${record.項目}: ${record.各類給付總額}`);
                            }
                        });
                        if (page.records.length > 2) {
                            console.log(`      ... 還有 ${page.records.length - 2} 筆記錄`);
                        }
                    }
                });
                
                // 檢查 currentTableData 中對應的記錄
                const jobRecords = currentTableData.filter(r => r.jobId === job.id);
                console.log(`  currentTableData 中的記錄: ${jobRecords.length} 筆`);
                
                const pageStats = {};
                jobRecords.forEach(r => {
                    const pageNum = r.頁碼 || 1;
                    pageStats[pageNum] = (pageStats[pageNum] || 0) + 1;
                });
                console.log(`  按頁碼分布:`, pageStats);
                
            } else if (json.records) {
                console.log(`  單頁格式: ${json.records.length} 筆記錄`);
            }
        });
        
        return true;
    },
    
    /**
     * 檢查 allJobs 資料
     */
    checkJobsData: function() {
        console.log('=== Jobs 資料檢查 ===');
        
        if (typeof allJobs === 'undefined') {
            console.error('❌ allJobs 未定義');
            return;
        }
        
        console.log('📊 Jobs 統計:');
        console.log('  - 總 Jobs 數:', allJobs.length);
        
        allJobs.forEach((job, index) => {
            console.log(`  - Job ${job.id}:`, {
                filename: job.original_filename,
                document_type: job.document_type,
                detected_stream: job.detected_stream,
                has_result_json: !!job.result_json,
                result_json_type: typeof job.result_json
            });
            
            // 檢查 result_json 結構
            if (job.result_json) {
                const json = job.result_json;
                if (json.頁面資料 && Array.isArray(json.頁面資料)) {
                    console.log(`    多頁格式: ${json.頁面資料.length} 頁`);
                    json.頁面資料.forEach((page, pageIndex) => {
                        const recordCount = page.records ? page.records.length : 0;
                        console.log(`      第 ${pageIndex + 1} 頁: ${recordCount} 筆記錄`);
                    });
                } else if (json.records) {
                    console.log(`    單頁格式: ${json.records.length} 筆記錄`);
                }
            }
        });
        
        return allJobs.map(job => ({
            id: job.id,
            filename: job.original_filename,
            has_result_json: !!job.result_json
        }));
    },
    
    /**
     * 模擬儲存操作（不實際發送請求）
     */
    simulateSave: function() {
        console.log('=== 模擬儲存操作 ===');
        
        if (typeof syncTableDataToCurrentData !== 'function') {
            console.error('❌ syncTableDataToCurrentData 函數不存在');
            return;
        }
        
        // 同步表格資料
        console.log('🔄 同步表格資料...');
        syncTableDataToCurrentData();
        
        // 檢查同步後的資料
        this.checkTableData();
        
        // 模擬分組邏輯
        console.log('🔄 模擬資料分組...');
        const jobDataMap = {};
        currentTableData.forEach(function (record) {
            if (!record.jobId) {
                console.warn('記錄缺少 jobId，跳過:', record);
                return;
            }

            if (!jobDataMap[record.jobId]) {
                jobDataMap[record.jobId] = [];
            }

            jobDataMap[record.jobId].push({
                項目: record.itemName,
                所得類別及代號: record.incomeType,
                各類給付總額: record.totalAmount.toString(),
                扣繳稅額: record.withholdingTax.toString()
            });
        });
        
        console.log('📊 分組結果:', jobDataMap);
        
        // 驗證資料完整性
        const totalRecords = Object.values(jobDataMap).reduce((sum, records) => sum + records.length, 0);
        console.log('✅ 資料完整性驗證:', {
            currentTableData: currentTableData.length,
            jobDataMap: totalRecords,
            match: totalRecords === currentTableData.length
        });
        
        // 🆕 模擬多頁資料重新分配
        console.log('🔄 模擬多頁資料重新分配...');
        allJobs.forEach(function(job) {
            if (!job.result_json || !jobDataMap[job.id]) return;
            
            const json = job.result_json;
            const updatedRecords = jobDataMap[job.id];
            
            if (json.頁面資料 && Array.isArray(json.頁面資料)) {
                console.log(`Job ${job.id} 多頁處理:`);
                console.log(`  原始頁數: ${json.頁面資料.length}`);
                console.log(`  更新記錄數: ${updatedRecords.length}`);
                
                // 按頁碼分組
                const recordsByPage = {};
                updatedRecords.forEach(function(record) {
                    const matchingRecords = currentTableData.filter(function(r) {
                        return r.jobId === job.id && 
                               r.itemName === record.項目 && 
                               r.incomeType === record.所得類別及代號;
                    });
                    
                    if (matchingRecords.length > 0) {
                        const pageNum = matchingRecords[0].頁碼 || 1;
                        if (!recordsByPage[pageNum]) {
                            recordsByPage[pageNum] = [];
                        }
                        recordsByPage[pageNum].push(record);
                    }
                });
                
                console.log(`  按頁碼分組結果:`, Object.keys(recordsByPage).map(pageNum => 
                    `第${pageNum}頁: ${recordsByPage[pageNum].length}筆`
                ).join(', '));
            }
        });
        
        return jobDataMap;
    },
    
    /**
     * 檢查頁面狀態
     */
    checkPageState: function() {
        console.log('=== 頁面狀態檢查 ===');
        
        const state = {
            isEditMode: typeof isEditMode !== 'undefined' ? isEditMode : 'undefined',
            isViewMode: typeof isViewMode !== 'undefined' ? isViewMode : 'undefined',
            currentDocType: typeof currentDocType !== 'undefined' ? currentDocType : 'undefined',
            withholdingView: typeof withholdingView !== 'undefined' ? withholdingView : 'undefined',
            viewMode: typeof viewMode !== 'undefined' ? viewMode : 'undefined',
            selectedJobId: typeof selectedJobId !== 'undefined' ? selectedJobId : 'undefined',
            caseId: typeof caseId !== 'undefined' ? caseId : 'undefined',
            jobIds: typeof jobIds !== 'undefined' ? jobIds : 'undefined'
        };
        
        console.log('📊 頁面狀態:', state);
        
        // 檢查表格顯示狀態
        const tableStates = {
            table401: $('#table-401').is(':visible'),
            table403: $('#table-403').is(':visible'),
            tableWithholding: $('#table-withholding').is(':visible')
        };
        
        console.log('📊 表格顯示狀態:', tableStates);
        
        // 檢查按鈕狀態
        const buttonStates = {
            editBtn: $('#edit-btn').is(':visible'),
            saveBtn: $('#save-btn').is(':visible'),
            createVersionBtn: $('#create-version-btn').is(':visible')
        };
        
        console.log('📊 按鈕狀態:', buttonStates);
        
        return {
            pageState: state,
            tableStates: tableStates,
            buttonStates: buttonStates
        };
    },
    
    /**
     * 匯出當前資料用於除錯
     */
    exportDebugData: function() {
        const debugData = {
            timestamp: new Date().toISOString(),
            pageState: this.checkPageState(),
            tableData: this.checkTableData(),
            jobsData: this.checkJobsData(),
            multiPageData: this.checkMultiPageData(),
            currentTableData: typeof currentTableData !== 'undefined' ? currentTableData : null,
            allJobs: typeof allJobs !== 'undefined' ? allJobs : null
        };
        
        const dataStr = JSON.stringify(debugData, null, 2);
        const blob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `tax_ocr_debug_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('✅ 除錯資料已匯出');
        return debugData;
    },
    
    /**
     * 顯示使用說明
     */
    help: function() {
        console.log('=== Tax OCR 除錯工具使用說明 ===');
        console.log('');
        console.log('可用命令:');
        console.log('  TaxOcrDebug.checkTableData()      - 檢查表格資料完整性');
        console.log('  TaxOcrDebug.checkMultiPageData()  - 檢查多頁資料完整性');
        console.log('  TaxOcrDebug.checkJobsData()       - 檢查 Jobs 資料');
        console.log('  TaxOcrDebug.simulateSave()        - 模擬儲存操作');
        console.log('  TaxOcrDebug.checkPageState()      - 檢查頁面狀態');
        console.log('  TaxOcrDebug.exportDebugData()     - 匯出除錯資料');
        console.log('  TaxOcrDebug.help()                - 顯示此說明');
        console.log('');
        console.log('多頁問題除錯流程:');
        console.log('1. TaxOcrDebug.checkMultiPageData() - 檢查多頁資料結構');
        console.log('2. TaxOcrDebug.checkTableData()     - 檢查表格資料頁碼分布');
        console.log('3. TaxOcrDebug.simulateSave()       - 模擬儲存看分組邏輯');
        console.log('4. TaxOcrDebug.exportDebugData()    - 匯出完整資料分析');
        console.log('');
        console.log('使用方式:');
        console.log('1. 開啟瀏覽器開發者工具 (F12)');
        console.log('2. 切換到 Console 標籤');
        console.log('3. 輸入上述命令並按 Enter');
    }
};

// 自動載入時顯示說明
console.log('🔧 Tax OCR 除錯工具已載入');
console.log('輸入 TaxOcrDebug.help() 查看使用說明');
console.log('多頁問題請使用 TaxOcrDebug.checkMultiPageData() 檢查');