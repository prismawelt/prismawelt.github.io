# Search metadata is generated separately from the visible article content.
require "json"
require "open3"
require "time"

module Prismawelt
  class Discovery < Jekyll::Generator
    safe true
    priority :low

    def generate(site)
      @site = site
      @base = site.config.fetch("url").sub(%r{/$}, "") + site.config.fetch("baseurl", "")
      @descriptions = site.data.fetch("descriptions", {})
      pages = site.pages.select { |page| %w[ko en ja].include?(page.data["lang"]) }
      pages.each { |page| decorate(page) }
      site.config["discovery_updated"] = pages.filter_map { |page| page.data["last_modified_at"] }.max
    end

    def absolute(path)
      @base + path
    end

    def last_modified(page)
      relative = page.path.sub(%r{\A#{Regexp.escape(@site.source)}/}, "")
      output, status = Open3.capture2("git", "log", "-1", "--format=%cI", "--", relative,
                                     chdir: @site.source, err: File::NULL)
      status.success? && !output.strip.empty? ? Time.iso8601(output.strip).iso8601 : nil
    rescue Errno::ENOENT, ArgumentError
      nil
    end

    def decorate(page)
      language = page.data.fetch("lang")
      canonical_path = page.data["redirect_to"] || page.url
      canonical = absolute(canonical_path)
      description = @descriptions[canonical_path] || page.data["intro"] ||
                    @site.config.fetch("descriptions").fetch(language)
      headline = page.data["title"]
      home = page.data["layout"] == "home"
      title = home || headline == "HOME" ? "Iheon Kim (김이헌) — prismawelt" :
              "#{headline} — prismawelt"
      modified = last_modified(page)
      images = {
        "/ko/nichijou/mono/" => "/assets/files/mono/mono1.png",
        "/ko/nichijou/koikaze_ed/" => "/assets/files/koikaze_ed/koikaze_ed1.png",
        "/ko/nichijou/onimai/" => "/assets/files/onimai/onimai3.jpg"
      }
      image = images[page.data["lang_ko"]]
      page.data.merge!(
        "canonical_url" => canonical,
        "seo_title" => title,
        "seo_description" => description,
        "seo_locale" => { "ko" => "ko_KR", "en" => "en_US", "ja" => "ja_JP" }.fetch(language),
        "seo_image" => image && absolute(image),
        "last_modified_at" => modified
      )

      person = {
        "@type" => "Person", "@id" => absolute("/#author"),
        "name" => "Iheon Kim", "alternateName" => ["김이헌", "金 利憲", "prismawelt"],
        "url" => absolute("/ko/"),
        "affiliation" => { "@type" => "CollegeOrUniversity", "name" => "POSTECH" },
        "sameAs" => ["https://github.com/prismawelt", "https://blog.naver.com/prismawelt"]
      }
      website = {
        "@type" => "WebSite", "@id" => absolute("/#website"),
        "name" => "prismawelt", "alternateName" => "Iheon Kim",
        "url" => absolute("/"), "inLanguage" => ["ko", "en", "ja"],
        "author" => { "@id" => person["@id"] }
      }
      webpage = {
        "@type" => home ? "ProfilePage" : (page.data["layout"] == "archive" ? "CollectionPage" : "WebPage"),
        "@id" => canonical + "#webpage", "url" => canonical,
        "name" => title, "description" => description, "inLanguage" => language,
        "isPartOf" => { "@id" => website["@id"] }
      }
      webpage["dateModified"] = modified if modified
      webpage["mainEntity"] = { "@id" => person["@id"] } if home
      graph = [person, website, webpage]

      if page.data["article"]
        article_type = page.data["section"] == "physics" ? "Article" : "BlogPosting"
        article = {
          "@type" => article_type, "@id" => canonical + "#article",
          "headline" => headline, "description" => description, "url" => canonical,
          "inLanguage" => language, "isAccessibleForFree" => true,
          "author" => { "@id" => person["@id"] },
          "mainEntityOfPage" => { "@id" => webpage["@id"] },
          "articleSection" => page.data["series"]
        }
        article["datePublished"] = page.data["date"].to_s[0, 10] if page.data["date"]
        article["dateModified"] = modified if modified
        article["image"] = [absolute(image)] if image
        original = absolute(page.data.fetch("lang_ko"))
        if language == "ko"
          article["workTranslation"] = %w[en ja].map do |lang|
            { "@type" => article_type, "@id" => absolute(page.data.fetch("lang_#{lang}")) + "#article",
              "url" => absolute(page.data.fetch("lang_#{lang}")), "inLanguage" => lang }
          end
        else
          article["translationOfWork"] = {
            "@type" => article_type, "@id" => original + "#article", "url" => original, "inLanguage" => "ko"
          }
        end
        webpage["mainEntity"] = { "@id" => article["@id"] }
        graph << article
      end
      page.data["structured_data"] = JSON.generate({ "@context" => "https://schema.org", "@graph" => graph })
                                            .gsub("<", '\\u003c')
    end
  end
end
