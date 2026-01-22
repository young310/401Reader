// Global JavaScript functions

// Show notification
// type: 'success', 'danger', 'warning', 'info'
// danger 類型的通知不會自動關閉，需要使用者手動點擊關閉
function showNotification(message, type) {
    type = type || 'info';
    var alertClass = 'alert-' + type;
    var iconClass = type === 'success' ? 'fa-check-circle' :
                   type === 'danger' ? 'fa-exclamation-circle' :
                   type === 'warning' ? 'fa-exclamation-triangle' :
                   'fa-info-circle';

    var notification = $('<div class="alert ' + alertClass + ' alert-dismissible" role="alert" style="position: fixed; top: 20px; right: 20px; z-index: 9999; min-width: 250px; max-width: 400px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); padding: 12px 30px 12px 15px; font-size: 14px;">' +
        '<button type="button" class="close" data-dismiss="alert" style="position: absolute; top: 8px; right: 10px;"><span>&times;</span></button>' +
        '<i class="fa ' + iconClass + '" style="margin-right: 8px;"></i>' +
        message +
        '</div>');

    $('body').append(notification);

    // danger 類型不自動關閉，需要使用者手動點擊關閉
    if (type !== 'danger') {
        setTimeout(function() {
            notification.fadeOut(function() {
                $(this).remove();
            });
        }, 3000);
    }
}

// Show loading spinner
function showLoading() {
    if ($('#loading-overlay').length === 0) {
        var overlay = $('<div id="loading-overlay" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 9998; display: flex; align-items: center; justify-content: center;">' +
            '<div style="background: white; padding: 30px; border-radius: 8px; text-align: center;">' +
            '<i class="fa fa-spinner fa-spin" style="font-size: 48px; color: #3498db;"></i>' +
            '<p style="margin-top: 15px; color: #2c3e50;">載入中...</p>' +
            '</div>' +
            '</div>');
        $('body').append(overlay);
    }
}

// Hide loading spinner
function hideLoading() {
    $('#loading-overlay').fadeOut(function() {
        $(this).remove();
    });
}

// Format date
function formatDate(dateString) {
    var date = new Date(dateString);
    return date.toLocaleDateString('zh-TW') + ' ' + date.toLocaleTimeString('zh-TW');
}

// Format number with commas
function formatNumber(num) {
    if (num === null || num === undefined || num === '') return '0';
    var n = parseFloat(num);
    if (isNaN(n)) return '0';
    return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Initialize when DOM is ready
$(document).ready(function() {
    // 移除全域 AJAX 錯誤處理器，避免與頁面特定的錯誤處理衝突
    // 每個 AJAX 請求應該自行處理錯誤

    // Prevent form double submission
    $(document).on('submit', 'form', function() {
        var $form = $(this);
        if ($form.data('submitted') === true) {
            return false;
        }
        $form.data('submitted', true);
        setTimeout(function() {
            $form.data('submitted', false);
        }, 3000);
    });
});

// Auto-dismiss flash messages after 5 seconds
$(document).ready(function() {
    setTimeout(function() {
        $('.flash-messages-container .alert').fadeOut(function() {
            $(this).remove();
        });
    }, 5000);
});
