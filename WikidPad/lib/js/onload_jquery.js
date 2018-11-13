console.log("JQUERY LOADED");

function toggleTable(caption) {
    table = $(caption).parent()
    table.find("tbody, thead").slideToggle();
    }

$("table.collapsable").each(function (index, table) {
    $(table.caption).click(function () {
        toggleTable($(this));
        });

    toggleTable(table.caption);
    });


function collapseElement(elem) {
    $(elem).before($(document.createElement("span")).text("+").attr({
        "data-target" : $(elem).attr("name")
    
    }).click(function () {
        console.log($(this));
        target_name = $(this).attr("data-target");
        target = $('[name="'+target_name+'"]');
        
        target.slideToggle();
        })).slideToggle();

}

$("div.collapsable").each(function (index, div) {
    collapseElement(div);
    });

// Enhance the onclick
function onClick(e) {
    // First check for selection and fire an event if needed
    checkSelection();
        console.log("NEW ONCLICK");

    // Left click
    if(e.button == 0) {
        if ( $("*:focus").is("textarea, input") ) {
            triggerEvent("MOUSE_CLICK//KEEP_FOCUS");
        } else {
            triggerEvent("MOUSE_CLICK");
        }

    } else if (e.button == 1) {
        // Middle click
        ctrl = "/FALSE"
        if (e.ctrlKey) {
            ctrl = "/TRUE"
        }
        triggerEvent("MOUSE_MIDDLE_CLICK" + ctrl);
        e.stopPropagation();
        e.preventDefault();
        e.stopImmediatePropagation();
        e.cancelBubble = true;
    }
}
 
