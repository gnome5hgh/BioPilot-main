package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;

import com.biopilot.literature.domain.LiteratureSearchResult;
import com.biopilot.literature.domain.PaperCandidate;
import com.biopilot.literature.domain.SearchQuery;
import com.biopilot.literature.service.LiteratureSearchService;
import com.biopilot.literature.service.provider.LiteratureProvider;
import java.util.List;
import org.junit.jupiter.api.Test;

/** 文献聚合：去重、截断、单源失败不拖垮整体。 */
class LiteratureSearchServiceTest {

    private static PaperCandidate paper(String id, String doi, String title) {
        return new PaperCandidate(id, title, "A", "2024", "J", doi, id, "", "", true,
                "", "", "fake", 0);
    }

    @Test
    void dedupesByDoiAndRespectsLimit() {
        LiteratureProvider p1 = new FakeProvider("a",
                List.of(paper("1", "10.1/x", "T1"), paper("2", "10.1/y", "T2")));
        LiteratureProvider p2 = new FakeProvider("b",
                List.of(paper("3", "10.1/x", "T1 duplicate"), paper("4", "", "T3")));
        LiteratureSearchService service = new LiteratureSearchService(List.of(p1, p2));

        LiteratureSearchResult result = service.searchForAgent(
                new SearchQuery("q", List.of(), null, null, 2));

        assertThat(result.results()).hasSize(2);
        assertThat(result.results().get(0).title()).isEqualTo("T1");
        assertThat(result.sources()).containsEntry("a", 2).containsEntry("b", 2);
    }

    @Test
    void oneProviderFailureKeepsOtherResults() {
        LiteratureProvider ok = new FakeProvider("ok", List.of(paper("1", "10.1/x", "T1")));
        LiteratureProvider bad = new LiteratureProvider() {
            @Override
            public String name() {
                return "bad";
            }

            @Override
            public List<PaperCandidate> search(SearchQuery query) {
                throw new IllegalStateException("timeout");
            }
        };
        LiteratureSearchService service = new LiteratureSearchService(List.of(ok, bad));

        LiteratureSearchResult result = service.searchForAgent(
                new SearchQuery("q", List.of(), null, null, 10));

        assertThat(result.results()).hasSize(1);
        assertThat(result.errors()).containsEntry("bad", "timeout");
        assertThat(result.sources()).containsEntry("bad", 0);
    }

    @Test
    void unknownSourceReturnsError() {
        LiteratureSearchService service = new LiteratureSearchService(
                List.of(new FakeProvider("ok", List.of())));
        LiteratureSearchResult result = service.searchForAgent(
                new SearchQuery("q", List.of("missing"), null, null, 10));
        assertThat(result.results()).isEmpty();
        assertThat(result.errors()).containsKey("sources");
    }

    private record FakeProvider(String name, List<PaperCandidate> rows)
            implements LiteratureProvider {
        @Override
        public List<PaperCandidate> search(SearchQuery query) {
            return rows;
        }
    }
}
