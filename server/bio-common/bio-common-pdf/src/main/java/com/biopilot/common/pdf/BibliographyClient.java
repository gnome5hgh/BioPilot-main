package com.biopilot.common.pdf;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayInputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

/** 书目查询客户端：DOI → CrossRef，arXiv id → arXiv API。

    网络失败、查不到、字段缺失一律返回 null / 空字段；调用方按「取不到就留空」
    处理，绝不用文件名或猜测补全。
*/
public final class BibliographyClient {

    private static final String CROSSREF = "https://api.crossref.org/works/";
    private static final String ARXIV = "https://export.arxiv.org/api/query?id_list=";
    private static final Duration TIMEOUT = Duration.ofSeconds(10);

    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(TIMEOUT)
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();

    /** 按 DOI 查 CrossRef。
     *
     * Args:
     *     doi: DOI（不带 https://doi.org/ 前缀）。
     *
     * Returns:
     *     PaperMeta: 查到的书目；失败返回 null。
     */
    public PaperMeta byDoi(String doi) {
        if (doi == null || doi.isBlank()) {
            return null;
        }
        try {
            String url = CROSSREF + URLEncoder.encode(doi.trim(), StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(TIMEOUT)
                    .header("Accept", "application/json")
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(request,
                    HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 300) {
                return null;
            }
            JsonNode message = mapper.readTree(response.body()).path("message");
            if (message.isMissingNode()) {
                return null;
            }
            return new PaperMeta(
                    firstText(message.path("title")),
                    authors(message.path("author")),
                    issuedYear(message.path("issued")),
                    firstText(message.path("container-title")),
                    doi.trim(),
                    "proceedings".equalsIgnoreCase(message.path("type").asText())
                            ? "inproceedings" : "article");
        } catch (Exception e) {
            return null;
        }
    }

    /** 按 arXiv id 查 arXiv API。
     *
     * Args:
     *     arxivId: arXiv id（如 2401.01234）。
     *
     * Returns:
     *     PaperMeta: 查到的书目；失败返回 null。
     */
    public PaperMeta byArxiv(String arxivId) {
        if (arxivId == null || arxivId.isBlank()) {
            return null;
        }
        try {
            String url = ARXIV + URLEncoder.encode(arxivId.trim(), StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(TIMEOUT)
                    .GET()
                    .build();
            HttpResponse<byte[]> response = client.send(request,
                    HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() >= 300) {
                return null;
            }
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            Document document = factory.newDocumentBuilder()
                    .parse(new ByteArrayInputStream(response.body()));
            NodeList entries = document.getElementsByTagNameNS("*", "entry");
            if (entries.getLength() == 0) {
                return null;
            }
            Element entry = (Element) entries.item(0);
            String title = firstText(entry, "title");
            String year = firstText(entry, "published");
            if (year.length() >= 4) {
                year = year.substring(0, 4);
            }
            List<String> names = new ArrayList<>();
            NodeList authorNodes = entry.getElementsByTagNameNS("*", "author");
            for (int i = 0; i < authorNodes.getLength(); i++) {
                Element author = (Element) authorNodes.item(i);
                String name = firstText(author, "name");
                if (!name.isBlank()) {
                    names.add(name);
                }
            }
            return new PaperMeta(
                    title, String.join(" and ", names), year,
                    firstText(entry, "journal_ref"), "", "article");
        } catch (Exception e) {
            return null;
        }
    }

    private String firstText(JsonNode array) {
        if (array == null || !array.isArray() || array.isEmpty()) {
            return "";
        }
        return array.get(0).asText("").replaceAll("\\s+", " ").trim();
    }

    private String authors(JsonNode authors) {
        if (authors == null || !authors.isArray()) {
            return "";
        }
        List<String> names = new ArrayList<>();
        for (JsonNode author : authors) {
            String family = author.path("family").asText("").trim();
            String given = author.path("given").asText("").trim();
            if (family.isEmpty() && given.isEmpty()) {
                continue;
            }
            names.add(given.isEmpty() ? family : family + ", " + given);
        }
        return String.join(" and ", names);
    }

    private String issuedYear(JsonNode issued) {
        JsonNode parts = issued.path("date-parts");
        if (parts.isArray() && !parts.isEmpty()) {
            JsonNode first = parts.get(0);
            if (first.isArray() && !first.isEmpty()) {
                return first.get(0).asText("");
            }
        }
        return "";
    }

    private String firstText(Element parent, String localName) {
        NodeList nodes = parent.getElementsByTagNameNS("*", localName);
        if (nodes.getLength() == 0) {
            return "";
        }
        return nodes.item(0).getTextContent().replaceAll("\\s+", " ").trim();
    }
}
