package com.biopilot.common.core.text;

import java.util.Locale;

/** 论文标题归一化：小写 + 去标点与空白，供标题匹配与去重共用。

    与 Python 侧 ``re.sub(r"[\s\W_]+", "", text.lower())`` 同口径：保留任意
    语言的字母与数字，其余字符（标点、空白、下划线、符号）全部丢弃。这样同一篇
    论文的标题在大小写、全半角标点、换行差异下仍能匹配，而正文内容不参与。
*/
public final class TitleNormalizer {

    private TitleNormalizer() {
    }

    /** 归一化标题；null/空串返回空串。

    Args:
        title: 原始标题。

    Returns:
        str: 仅由字母与数字组成的归一化串。
    */
    public static String normalize(String title) {
        if (title == null || title.isEmpty()) {
            return "";
        }
        return title.toLowerCase(Locale.ROOT).replaceAll("[^\\p{L}\\p{N}]", "");
    }
}
